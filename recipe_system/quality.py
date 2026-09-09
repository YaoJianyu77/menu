"""Read-only, reproducible source-coverage and normalization audits."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from .core import atomic_json, load_yaml, now, read_jsonl

STATUS_MAP = {
    "blocked": "BLOCKED",
    "unsupported": "UNSUPPORTED",
    "disabled": "NOT_A_RECIPE_SOURCE",
    "not-a-recipe-source": "NOT_A_RECIPE_SOURCE",
}
NOISE = re.compile(
    r"^(?:[\s#|\-:]*|advertisement|reply(?: ↓)?|pinterest|facebook|twitter|metric|us|adjust|"
    r"quantity\|ingredient|add all ingredients to list|flag if inappropriate|"
    r"note: recipe directions are for original size|\d+(?:/\d+)?)$",
    re.IGNORECASE,
)
DESSERT = re.compile(
    r"\b(?:cookies?|brownies?|cake|fudge|icing|frosting|dessert)\b|蛋糕|饼干", re.IGNORECASE
)
DOC_NAMES = {
    "readme",
    "readme_header",
    "agents",
    "claude",
    "contributing",
    "contributers",
    "credits",
    "code_of_conduct",
    "code-of-conduct",
    "security",
    "maintainers",
    "development",
    "changelog",
    "index",
    "writing",
    "about",
    "template",
    "license",
    "copying",
}
EXCLUSION_REASONS = {
    "panozzaj--recipes": "Explicit archive/link lists, meal-planning notes, tips and book notes; not standalone recipe files.",
    "obfuscurity--food-recipes": "Cocktail recipe excluded by drinks-only source type, independently of meal preferences.",
    "dolph--recipes": "Index, measurement cheat sheet, holiday menus and cocktails explicitly outside authored meal recipe scope.",
    "DEAD10C5--1337-Noms-The-Hacker-Cookbook": "Administration/template documents, cookware project and drinks excluded by source type.",
    "sinker--tacofancy": "Per-directory README indexes excluded; individual components and full tacos are retained.",
}


REVIEWED_AUXILIARY = {
    (
        "reaper47--recipya",
        "deploy/fdc.db.zip",
    ): "Ingredient nutrient database, not recipes: internal/services/service.go Nutrients explicitly reads the FDC database; archive is a Git LFS pointer, not a recipe corpus.",
    (
        "TandoorRecipes--recipes",
        "web_server_faq.md",
    ): "Inspected Webserver Setup FAQ: reverse proxy, SSL/TLS and server requirements, no recipe content.",
}


def matches(path, patterns):
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def candidate_outside_scope(path):
    """Conservative flag for human review, never an automatic non-recipe decision."""
    p = Path(path)
    lower = path.lower()
    if p.suffix.lower() in {".zip", ".gz", ".paprikarecipe", ".recipe"}:
        return True
    if p.stem.lower() in DOC_NAMES or any(part.startswith(".") for part in p.parts):
        return False
    if any(
        part in p.parts
        for part in (
            "docs",
            "tips",
            "basics",
            "experiments",
            "templates",
            "_layouts",
            "_includes",
            "_posts",
            "l10n",
            "locale",
            "lang",
            "frontend",
            "vue3",
            "calculator",
            "flowchart",
            "http.d",
            "nginx",
        )
    ):
        return False
    if p.suffix.lower() in {".md", ".markdown", ".mdx"}:
        return True
    if p.suffix.lower() == ".csv":
        return "migration" in lower or "recipe" in p.stem.lower()
    if p.suffix.lower() in {".json", ".html"}:
        return (
            any(
                marker in lower
                for marker in (
                    "testdata/",
                    "test_data/",
                    "tests/data/",
                    "res_jsonld/",
                    "res_microdata/",
                )
            )
            and "report" not in lower
        )
    return False


def coverage_status(source_status, pending, unresolved_failures, gaps, discovery_error=None):
    if source_status in STATUS_MAP:
        return STATUS_MAP[source_status]
    if discovery_error:
        return "BLOCKED"
    return "PARTIAL" if pending or unresolved_failures or gaps else "COMPLETE"


def item_classification(key, failure, outcomes):
    return failure.get("classification") or outcomes.get(key, {}).get("classification")


def source_coverage(root="."):
    root = Path(root)
    config = load_yaml(root / "config/recipe-sources.yaml")
    states = [
        json.loads(path.read_text())
        for path in sorted((root / "state/recipes").glob("recipe-agent-*.json"))
    ]
    outcomes = {
        row["key"]: row
        for name in ("outcomes.jsonl", "new-source-failures.jsonl")
        for row in read_jsonl(root / "state/recipes/recovery" / name)
    }
    processed, failures, owned, archives = {}, {}, {}, {}
    plan_path = root / "state/recipes/plan.json"
    if plan_path.exists():
        for agent, units in json.loads(plan_path.read_text())["partitions"].items():
            for unit in units:
                for path in unit["paths"]:
                    owned.setdefault(unit["source"]["id"] + ":" + path, []).append(agent)
    for state in states:
        archives.update(state.get("archive_members", {}))
        for key in state.get("processed", {}):
            processed[key] = state["processed"][key]
        failures.update(state.get("failures", {}))
    results = []
    for source in config["sources"]:
        prefix = source["id"] + ":"
        record = {
            "id": source["id"],
            "url": source["url"],
            "revision": source.get("revision"),
            "configured_status": source["status"],
            "reason": source["reason"],
            "retrieved_index_entries": source.get("discovered_index_items"),
        }
        files, error = [], None
        cache = root / ".cache/recipes" / source["id"]
        if (cache / ".git").exists() and source.get("revision"):
            result = subprocess.run(
                ["git", "-C", str(cache), "ls-tree", "-rz", "--name-only", source["revision"]],
                capture_output=True,
                check=False,
            )
            if result.returncode:
                error = result.stderr.decode(errors="replace")
            else:
                files = result.stdout.decode().rstrip("\0").split("\0")
        elif source["status"] == "enabled":
            error = (
                "Pinned source cache is unavailable; source coverage cannot be established offline."
            )
        selected = {
            path
            for path in files
            if matches(path, source.get("include", []))
            and not matches(path, source.get("exclude", []))
        }
        excluded = [path for path in files if matches(path, source.get("exclude", []))]
        outside = sorted(set(files) - selected - set(excluded))
        gaps = (
            [
                path
                for path in outside
                if candidate_outside_scope(path) and (source["id"], path) not in REVIEWED_AUXILIARY
            ]
            if source["status"] == "enabled"
            else []
        )
        successful = {path for path in selected if prefix + path in processed}
        failed = {path: failures[prefix + path] for path in selected if prefix + path in failures}
        nonrecipe = {
            path
            for path, failure in failed.items()
            if item_classification(prefix + path, failure, outcomes) == "NOT_A_RECIPE_SOURCE"
        }
        pending = sorted(selected - successful - set(failed))
        source_archives = {
            key: values for key, values in archives.items() if key.startswith(prefix)
        }
        unresolved_archive_members = [
            dict(member, container=key[len(prefix) :])
            for key, members in source_archives.items()
            for member in members
            if member["status"] in {"failed", "partial", "unsupported"}
            and item_classification(key, failures.get(key, {}), outcomes) != "NOT_A_RECIPE_SOURCE"
        ]
        member_counts = dict(
            Counter(member["status"] for members in source_archives.values() for member in members)
        )
        record.update(
            status=coverage_status(
                source["status"],
                pending,
                set(failed) - nonrecipe,
                gaps or unresolved_archive_members,
                error,
            ),
            pinned_tree_file_count=len(files) if files else None,
            declared_candidate_files=len(selected),
            configured_estimate=source.get("estimated_items"),
            configured_estimate_matches_tree=(source.get("estimated_items") == len(selected))
            if source["status"] == "enabled"
            else None,
            deliberately_excluded_source_files=len(files)
            if source["status"] in {"disabled", "not-a-recipe-source"}
            else 0,
            archive_containers=source.get(
                "archive_containers", source.get("unsupported_containers", [])
            ),
            archive_member_status_counts=member_counts,
            unresolved_archive_members=unresolved_archive_members,
            successful_candidate_files=len(successful),
            failed_candidate_files=len(failed),
            confidently_nonrecipe_failures=len(nonrecipe),
            unresolved_failed_files=sorted(set(failed) - nonrecipe),
            pending_candidate_files=pending,
            explicit_exclusion_count=len(excluded),
            explicit_exclusion_paths=sorted(excluded),
            exclusion_reason=EXCLUSION_REASONS.get(
                source["id"], "No explicit candidate exclusions configured."
            ),
            auxiliary_file_count=len(outside) - len(gaps),
            individually_reviewed_auxiliary=[
                {"path": path, "reason": REVIEWED_AUXILIARY[(source["id"], path)]}
                for path in outside
                if (source["id"], path) in REVIEWED_AUXILIARY
            ],
            auxiliary_reason="Outside corpus: code, assets, configuration, licenses, index documents, cooking technique/reference material; potential recipe data is separately flagged.",
            potential_unexplored_candidate_count=len(gaps),
            potential_unexplored_candidate_paths=gaps,
            file_accounting_complete=bool(selected) and not pending,
            extraction_complete=bool(selected)
            and not pending
            and not (set(failed) - nonrecipe)
            and not gaps
            and not unresolved_archive_members,
            discovery_error=error,
        )
        results.append(record)
    report = {
        "audit_version": 1,
        "audited_at": now(),
        "index_revision": config["index_revision"],
        "semantics": "COMPLETE means selected corpus extraction is resolved and no potential omitted candidates remain. File accounting alone does not establish extraction completeness. Unknown failures are not classified as non-recipes.",
        "status_counts": dict(sorted(Counter(row["status"] for row in results).items())),
        "ownership_collisions": {
            key: agents for key, agents in owned.items() if len(set(agents)) > 1
        },
        "sources": results,
    }
    atomic_json(root / "docs/source-coverage.json", report)
    return report


CUISINE_GROUPS = {
    "italian": ("italian", "italien", "italiano", "italiana", "italienisch"),
    "french": ("french", "français", "française", "francais", "franzoesisch", "französisch"),
    "turkish_mediterranean": (
        "turkish",
        "türk",
        "mediterranean",
        "mediterráneo",
        "mediterranea",
        "greek",
        "lebanese",
    ),
    "chinese_asian": (
        "chinese",
        "asian",
        "japanese",
        "korean",
        "thai",
        "vietnamese",
        "indian",
        "indonesian",
        "filipino",
        "malaysian",
        "singaporean",
        "cantonese",
        "sichuan",
        "chinois",
        "asiatique",
        "中国",
        "中式",
        "亚洲",
    ),
}


def cuisine_basis(recipe, group):
    explicit = str(recipe.get("cuisine") or "").casefold()
    if any(term in explicit for term in CUISINE_GROUPS[group]):
        return {"kind": "explicit-source-cuisine", "value": recipe["cuisine"]}
    if group == "chinese_asian" and any(
        name in recipe.get("source", "") for name in ("Anduin2017/HowToCook", "YunYouJun/cook")
    ):
        return {
            "kind": "source-collection-inference",
            "value": "Chinese-language home-cooking collection; actual dish cuisine remains unverified",
        }
    return None


def select_cohorts(recipes, matches_rows):
    """Requested cohorts are selections for inspection, not extra ranking decisions."""
    by_id = {recipe["id"]: recipe for recipe in recipes}
    joined = [
        (by_id[match["recipe_id"]], match)
        for match in matches_rows
        if match["recipe_id"] in by_id and match.get("ranking_representative", True)
    ]
    joined.sort(key=lambda pair: (-pair[1]["total_score"], pair[0]["id"]))
    groups = {"overall_top_20": (joined, 20)}
    for group in CUISINE_GROUPS:
        groups[group + "_top_10"] = ([pair for pair in joined if cuisine_basis(pair[0], group)], 10)
    groups["air_fryer_top_10"] = (
        [pair for pair in joined if "air fryer" in pair[0].get("cooking_method", [])],
        10,
    )
    groups["under_20_minutes_top_10"] = (
        [
            pair
            for pair in joined
            if isinstance(pair[0].get("total_minutes"), (int, float))
            and pair[0]["total_minutes"] < 20
        ],
        10,
    )
    groups["low_scoring_rejected_10"] = (
        list(
            reversed(
                [
                    pair
                    for pair in joined
                    if pair[1].get("status") == "rejected"
                    or pair[1].get("recommendation_status") == "not-recommended"
                ]
            )
        ),
        10,
    )
    result = {}
    for name, (pairs, limit) in groups.items():
        items = []
        for recipe, match in pairs[:limit]:
            quality = match.get("quality", {})
            flags = []
            if quality.get("quality_issues"):
                flags.append("extraction-quality-issues")
            if quality.get("meal_role") in {"dessert", "condiment", "drink", "bread", "component"}:
                flags.append("not-a-complete-main-meal")
            if any(
                NOISE.fullmatch(item["canonical_ingredient"].strip())
                for item in recipe["ingredients"]
            ):
                flags.append("obvious-noningredient-row")
            if recipe.get("active_minutes") is None:
                flags.append("active-time-unknown")
            group = name.removesuffix("_top_10")
            items.append(
                {
                    "recipe_id": recipe["id"],
                    "title": recipe["title"],
                    "score": match["total_score"],
                    "status": match.get("status"),
                    "recommendation_status": match.get("recommendation_status"),
                    "cuisine": recipe.get("cuisine"),
                    "cuisine_selection_basis": cuisine_basis(recipe, group)
                    if group in CUISINE_GROUPS
                    else None,
                    "active_minutes": recipe.get("active_minutes"),
                    "total_minutes": recipe.get("total_minutes"),
                    "major_protein": recipe.get("major_protein"),
                    "meal_role": quality.get("meal_role"),
                    "ingredients": [item["display"] for item in recipe["ingredients"]],
                    "instructions": recipe.get("instructions", []),
                    "source_url": recipe.get("original_source_url") or recipe["source_url"],
                    "automated_flags": flags,
                    "manual_review": None,
                }
            )
        result[name] = {
            "available_count": len(pairs),
            "selected_count": len(items),
            "requested_count": limit,
            "items": items,
        }
    return result


def normalization_audit(root="."):
    root = Path(root)
    rows = read_jsonl(root / "data/recipes/normalized/recipes.jsonl")
    match_rows = read_jsonl(root / "data/matches/results.jsonl")
    by_id = {row["id"]: row for row in rows}
    unresolved = Counter()
    noisy, examples = [], []
    ingredients = 0
    for row in rows:
        noise = []
        for item in row["ingredients"]:
            ingredients += 1
            name = item["canonical_ingredient"]
            if item.get("normalization_method") == "unresolved-name":
                unresolved[name] += 1
            if NOISE.fullmatch(name.strip()):
                noise.append({"canonical": name, "original": item["original_text"]})
        if noise:
            noisy.append(row["id"])
            if len(examples) < 30:
                examples.append(
                    {
                        "recipe_id": row["id"],
                        "title": row["title"],
                        "source_url": row["source_url"],
                        "noise": noise[:8],
                    }
                )
    top = sorted(match_rows, key=lambda row: (-row["total_score"], row["recipe_id"]))[:50]
    cohort = []
    for match in top:
        recipe = by_id[match["recipe_id"]]
        cohort.append(
            {
                "recipe_id": recipe["id"],
                "title": recipe["title"],
                "score": match["total_score"],
                "status": match["status"],
                "dessert_title_signal": bool(DESSERT.search(recipe["title"])),
                "active_minutes": recipe.get("active_minutes"),
                "total_minutes": recipe.get("total_minutes"),
                "cuisine": recipe.get("cuisine"),
                "meal_type": recipe.get("meal_type"),
                "protein": recipe.get("major_protein"),
                "source_url": recipe["source_url"],
            }
        )
    previous_path = root / "docs/normalization-audit.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    report = {
        "manual_review_passes": previous.get("manual_review_passes", []),
        "audit_version": 1,
        "audited_at": now(),
        "recipes": len(rows),
        "ingredient_rows": ingredients,
        "missing_active_time": sum(row.get("active_minutes") is None for row in rows),
        "missing_total_time": sum(row.get("total_minutes") is None for row in rows),
        "missing_cuisine": sum(not row.get("cuisine") for row in rows),
        "missing_meal_type": sum(not row.get("meal_type") for row in rows),
        "unresolved_ingredient_rows": sum(unresolved.values()),
        "top_unresolved_names": [
            {"name": name, "count": count} for name, count in unresolved.most_common(80)
        ],
        "recipes_with_obvious_noningredient_rows": len(noisy),
        "noisy_recipe_ids": noisy,
        "examples": examples,
        "top_50": cohort,
        "requested_cohorts": select_cohorts(rows, match_rows),
        "recommended_general_changes": [
            "Re-extract structured source ingredients centrally from immutable raw text; never alter original records to fix parser output.",
            "Drop markup-only separators and known navigation labels from derived ingredient lists with explicit exclusion evidence; quarantine remaining malformed extraction.",
            "Parse ingredient tables by column and join wrapped continuation lines before quantity and alias normalization.",
            "Preserve prep/cook/rest times separately; active time remains unknown unless explicitly supported, never equate prep and active automatically.",
            "Infer meal type only from explicit categories or transparent source-path/title rules; keep desserts, drinks, sauces and components collected but separate from everyday main-meal ranking.",
            "Use ingredients as nutrition proxies only with meal context and sufficient quantity evidence; an egg in a cookie is not evidence of a balanced main meal.",
            "Choose major protein using substantive quantities and source recipe context rather than first canonical protein in ingredient order.",
            "Keep cuts, dried/fresh herbs, generic oil and specific oils distinct; substitutions require a separate explicit rule.",
        ],
    }
    atomic_json(root / "docs/normalization-audit.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["coverage", "normalization", "all"])
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    if args.action in {"coverage", "all"}:
        source_coverage(args.root)
    if args.action in {"normalization", "all"}:
        normalization_audit(args.root)


if __name__ == "__main__":
    main()
