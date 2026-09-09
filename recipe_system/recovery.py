"""Audit preserved failures and retry only structurally recoverable owned items."""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import re
from pathlib import Path

from .core import atomic_json, now, read_jsonl, write_jsonl
from .recipes import RecipeSourceAgent, git, parse_content

VERSION = "layout-recovery-v2"


def content(root, row):
    path = row["failure"]["item_identifier"]
    payload = git(
        root / ".cache/recipes" / row["source_id"],
        "show",
        row["revision"] + ":" + path,
        binary=True,
    )
    if path.endswith(".gz"):
        payload = gzip.decompress(payload)
    return payload.decode("utf-8", errors="replace")


def classify(text, path):
    """Uncertain pages stay unsupported; lack of parse is not nonrecipe evidence."""
    body = "\n".join(text.splitlines()[1:]) if path.endswith(".gz") else text
    if len(body.strip()) < 600 and re.search(
        r"(?i)access denied|403 forbidden|enable javascript|captcha|robot check|just a moment|request blocked",
        body,
    ):
        return (
            "BLOCKED",
            "captured-access-or-missing-page",
            "Short cached response explicitly reports access/error rather than recipe content.",
        )
    visible = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip()
    if re.fullmatch(r"\s*#[^\n]*(?:\n\s*(?:`?TODO`?|See \[[^\]]+\]\([^)]*\)\.?))?\s*", visible):
        return (
            "NOT_A_RECIPE_SOURCE",
            "duplicate/non-recipe-file",
            "Heading-only TODO or explicit pointer-only record; no actual recipe body.",
        )
    if re.search(
        r"%(?:INGREDIENT|INSTRUCTION|IMAGE)_NAME%|Sample recipe name|<title>asdf</title>", text
    ):
        return (
            "NOT_A_RECIPE_SOURCE",
            "repository-metadata",
            "Synthetic parser fixture contains replacement tokens or explicit sample/asdf title.",
        )
    if path.endswith(".gz") and len(body.strip()) < 250:
        return (
            "UNSUPPORTED",
            "incomplete-cached-content",
            "Cached response too short to establish a complete recipe; not inferred nonrecipe.",
        )
    if path.endswith((".html", ".htm")):
        return (
            "UNSUPPORTED",
            "HTML",
            "HTML lacks a supported complete Recipe payload or explicit component layout.",
        )
    if path.endswith(".gz"):
        if re.search(r"(?im)^\s*(?:recipe )?ingredients\b", text):
            return (
                "LEGITIMATE_RECIPE_FAILURE",
                "instructions-parser-failure",
                "Explicit ingredient section but no confidently bounded complete ingredient/method extraction.",
            )
        return (
            "UNSUPPORTED",
            "unlabelled-or-index-archive",
            "Archive may be a recipe, roundup, navigation or prose; no confident complete structure.",
        )
    if re.search(
        r"(?im)^\s*(?:#+\s*)?(?:ingredients|instructions|directions|steps|recipe|材料)\b|^\s*[-*+]\s+\d",
        text,
    ):
        return (
            "LEGITIMATE_RECIPE_FAILURE",
            "alternate-markdown-layout",
            "Recipe component evidence exists but required sections cannot both be reliably extracted.",
        )
    return (
        "UNSUPPORTED",
        "other",
        "Insufficient structural evidence to distinguish a recipe from an index or narrative.",
    )


def audit(root=Path("."), *, outcomes_only=False):
    root = Path(root)
    directory = root / "state/recipes/recovery"
    baseline = read_jsonl(directory / "baseline.jsonl")
    processed = {
        key: ids
        for p in (root / "state/recipes").glob("recipe-agent-*.json")
        for key, ids in json.loads(p.read_text())["processed"].items()
    }
    output = []
    roots = collections.Counter()
    categories = collections.Counter()
    for row in baseline:
        text = content(root, row)
        path = row["failure"]["item_identifier"]
        classification, cause, evidence = classify(text, path)
        roots[cause] += 1
        recovered = row["key"] in processed
        categories["recovered" if recovered else classification] += 1
        output.append(
            dict(
                row,
                classification="RECOVERED" if recovered else classification,
                root_cause=cause,
                evidence=(
                    "Checkpoint records successful raw collection: "
                    + ", ".join(processed[row["key"]])
                )
                if recovered
                else evidence,
                original_diagnosis=evidence,
                recovered_raw_ids=processed.get(row["key"], []),
                parser_version=VERSION,
            )
        )
    write_jsonl(directory / "outcomes.jsonl", output)
    result = {
        "initial_failures": len(baseline),
        "recovered": categories["recovered"],
        "remaining_legitimate_recipe_failures": categories["LEGITIMATE_RECIPE_FAILURE"],
        "non_recipe_candidates_correctly_rejected": categories["NOT_A_RECIPE_SOURCE"],
        "unsupported": categories["UNSUPPORTED"],
        "blocked": categories["BLOCKED"],
        "remaining_total": len(baseline) - categories["recovered"],
        "by_root_cause": dict(sorted(roots.items())),
        "classification_criterion": "Confident nonrecipe only explicit TODO/pointer or synthetic fixture tokens. Ambiguous index/prose remains unsupported. Explicit ingredient/component evidence without a complete parse is legitimate failure. Historical access responses remain blocked; no network retry bypass.",
        "parser_version": VERSION,
    }
    if outcomes_only:
        return result
    atomic_json(directory / "summary.json", result)
    atomic_json(
        directory / "breakdown.json",
        {
            "initial_failures": len(baseline),
            "by_root_cause": dict(sorted(roots.items())),
            "by_source": dict(
                sorted(collections.Counter(r["source_id"] for r in baseline).items())
            ),
            "by_initial_error": dict(
                collections.Counter(r["failure"]["error_message"] for r in baseline)
            ),
            "criterion": result["classification_criterion"],
        },
    )
    return result


def retry(agent, root=Path(".")):
    root = Path(root)
    baseline = read_jsonl(root / "state/recipes/recovery/baseline.jsonl")
    state = json.loads((root / "state/recipes" / f"{agent}.json").read_text())
    candidates = set()
    for row in baseline:
        if row["agent"] != agent or row["key"] not in state["failures"]:
            continue
        parsed = parse_content(
            content(root, row), row["source_id"] + "/" + row["failure"]["item_identifier"]
        )
        if parsed and all(r.get("ingredients") and r.get("instructions") for r in parsed):
            candidates.add(row["key"])
    plan = json.loads((root / "state/recipes/plan.json").read_text())
    units = [
        dict(u, paths=[p for p in u["paths"] if u["source"]["id"] + ":" + p in candidates])
        for u in plan["partitions"][agent]
    ]
    before = len(state["failures"])
    final = RecipeSourceAgent(root, agent).collect(
        [u for u in units if u["paths"]], retry_failures=True
    )
    report = {
        "agent": agent,
        "parser_version": VERSION,
        "timestamp": now(),
        "affected_failed_items": len(candidates),
        "recovered": before - len(final["failures"]),
        "remaining": len(final["failures"]),
        "method": "Retry only baseline failed items accepted by generalized adapter. Prior successful records untouched; error history retained.",
    }
    report_path = root / "state/recipes/recovery" / f"{agent}.json"
    previous = json.loads(report_path.read_text()) if report_path.exists() else None
    history = previous.get("improvements", [previous]) if previous else []
    atomic_json(report_path, dict(report, improvements=history + [report]))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["audit", "retry"])
    parser.add_argument("--agent", default="recipe-agent-01")
    args = parser.parse_args()
    print(json.dumps(retry(args.agent) if args.action == "retry" else audit(), indent=2))


if __name__ == "__main__":
    main()
