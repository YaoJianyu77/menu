"""Offline schema, accounting, provenance and reproducibility checks."""

import json
from pathlib import Path

from .core import read_jsonl, validate_record
from .match import match_recipes
from .normalize import FORBIDDEN


def validate(root):
    root = Path(root)
    counts = {}
    kinds = {
        "data/recipes/raw/*.jsonl": "raw-recipe",
        "data/recipes/normalized/recipes.jsonl": "normalized-recipe",
        "data/recipes/merged.jsonl": "raw-recipe",
        "data/recipes/normalized/quality-issues.jsonl": "normalization-issue",
        "data/foodlion/evidence/products.jsonl": "evidence-product",
        "data/foodlion/evidence/ingredients.jsonl": "evidence-ingredient",
        "state/recipes/recovery/*.jsonl": "recovery-item",
        "data/foodlion/raw/*.jsonl": "product",
        "data/foodlion/products.jsonl": "product",
        "data/foodlion/ingredients.jsonl": "ingredient",
        "data/matches/results.jsonl": "match",
        "data/recipes/duplicates/*.jsonl": "duplicate",
        "state/recipes/*-index.jsonl": "source-index",
        "snapshots/foodlion/*/raw/*.jsonl": "product",
        "snapshots/foodlion/*/products.jsonl": "product",
        "snapshots/foodlion/*/ingredients.jsonl": "ingredient",
    }
    for pattern, kind in kinds.items():
        for path in sorted(root.glob(pattern)):
            rows = read_jsonl(path)
            for row in rows:
                validate_record(row, kind)
            counts[str(path.relative_to(root))] = len(rows)
    raw = {
        row["id"]: row
        for path in (root / "data/recipes/raw").glob("*.jsonl")
        for row in read_jsonl(path)
    }
    normalized = read_jsonl(root / "data/recipes/normalized/recipes.jsonl")
    for recipe in normalized:
        assert recipe["raw_id"] in raw, f"Orphan normalized recipe {recipe['id']}"
        assert recipe["source_url"] == raw[recipe["raw_id"]]["source_url"]
        assert recipe["source_license"] == raw[recipe["raw_id"]]["source_license"]
    owners = {}
    for path in sorted((root / "state/recipes").glob("recipe-agent-*.json")):
        state = json.loads(path.read_text())
        assert state["agent"] == path.stem
        for key in list(state["processed"]) + list(state["failures"]):
            assert key not in owners, f"Cross-shard ownership collision: {key}"
            owners[key] = path.stem
        for key, ids in state["processed"].items():
            assert all(rid in raw for rid in ids), f"Checkpoint missing durable records: {key}"
        assert not (set(state["processed"]) & set(state["failures"]))
    manifest_path = root / "state/recipes/manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest["completion_status"].startswith("complete"):
            assert (
                manifest["candidate_files_discovered"]
                == manifest["candidate_files_processed"] + manifest["candidate_files_failed"]
            )
            assert manifest["sources_enabled"] == manifest["sources_completed"]
    products = {p["id"]: p for p in read_jsonl(root / "data/foodlion/products.jsonl")}
    for ingredient in read_jsonl(root / "data/foodlion/ingredients.jsonl"):
        assert all(pid in products for pid in ingredient["product_ids"])
        assert ingredient["product_count"] == len(ingredient["product_ids"])
    catalog_products = {
        p["product_id"]: p for p in read_jsonl(root / "data/foodlion/evidence/products.jsonl")
    }
    if catalog_products:
        from .evidence import validate_evidence

        validate_evidence(root)
    for result in read_jsonl(root / "data/matches/results.jsonl"):
        assert result["recipe_id"] in raw
        for item in result["ingredient_matches"]:
            if item["status"] == "verified_available":
                assert item["product_ids"] and item["snapshot_id"] and item["store_id"]
                assert all(pid in products for pid in item["product_ids"])
            elif item["status"] == "likely_available":
                assert item["product_ids"] and item["evidence"]
                assert all(
                    pid in catalog_products or pid in products for pid in item["product_ids"]
                )
                assert all(e.get("source_url") and e.get("retrieved_at") for e in item["evidence"])
            elif item["status"] == "unknown":
                assert not item["product_ids"]
        assert result["total_ingredients"] == sum(
            result[key]
            for key in [
                "verified_ingredient_count",
                "likely_ingredient_count",
                "unknown_ingredient_count",
                "unsupported_ingredient_count",
            ]
        )
    for path in (root / "snapshots/foodlion").glob("*/manifest.json"):
        manifest = json.loads(path.read_text())
        if manifest["completion_status"] == "complete":
            assert manifest["discovery_complete"]
            assert manifest["configured_store"]["store_id"]
            assert len(manifest["categories_completed"]) == len(manifest["categories_discovered"])
    match_path = root / "data/matches/results.jsonl"
    if match_path.exists():
        before = match_path.read_bytes()
        match_recipes(root)
        assert before == match_path.read_bytes(), "Matcher is not reproducible"
    from .publish import visible_text

    for path in (root / "site/dist").rglob("*.html"):
        assert not FORBIDDEN.search(visible_text(path.read_text())), (
            f"Forbidden output unit in {path}"
        )
    content = root / "site/content/recipes.json"
    if content.exists():

        def check_content(value, key=""):
            if key in {
                "source",
                "source_url",
                "original_source_url",
                "source_license_url",
                "evidence_source_url",
                "source_path",
                "archive_member",
                "url",
            }:
                return
            if isinstance(value, dict):
                for child_key, child in value.items():
                    check_content(child, child_key)
            elif isinstance(value, list):
                for child in value:
                    check_content(child)
            elif isinstance(value, str):
                assert not FORBIDDEN.search(value), f"Forbidden unit in published field {key}"

        check_content(json.loads(content.read_text()))
    result = {
        "validated_files": len(counts),
        "records": sum(counts.values()),
        "counts": counts,
        "provenance": "verified",
        "ownership": "verified",
        "determinism": "verified",
    }
    if (root / "site/content/catalog-manifest.json").exists():
        from .catalog_validation import validate_catalog

        result["catalog"] = validate_catalog(root)
    return result
