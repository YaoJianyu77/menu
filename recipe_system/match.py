"""Explainable deterministic scoring. Unknown inventory never becomes availability."""

import json
from pathlib import Path

from .core import load_yaml, read_jsonl, stable_id, write_jsonl


def falling(value, good, bad):
    return max(0, min(1, (bad - value) / max(1, bad - good)))


def evaluate(recipe, inventory, preferences, aliases, snapshot=None):
    snapshot = snapshot or {}
    complete_catalog = (
        bool(snapshot.get("discovery_complete"))
        and snapshot.get("completion_status") == "complete"
        and not snapshot.get("failures")
    )
    p = preferences
    s = p["scoring"]
    weights = s["weights"]
    by_name = {row.get("canonical_ingredient", row.get("name")): row for row in inventory}
    matches = []
    unique = {}
    for ingredient in recipe["ingredients"]:
        name = ingredient["canonical_ingredient"]
        unique[name] = unique.get(name, True) and bool(ingredient.get("optional", False))
    for name, optional in sorted(unique.items()):
        evidence = by_name.get(name)
        # Absence from a catalog is not evidence of out of stock; availability is unknown.
        available = (
            evidence.get("currently_available")
            if evidence
            else (False if complete_catalog else None)
        )
        product_ids = (
            evidence.get("product_ids", evidence.get("matching_product_ids", []))
            if evidence
            else []
        )
        supported = (
            bool(product_ids)
            and available is True
            and bool(evidence.get("store_id"))
            and bool(evidence.get("snapshot_id"))
            and bool(evidence.get("last_verified_at", evidence.get("last_verified_timestamp")))
        )
        status = (
            "available"
            if supported
            else (
                ("missing-optional" if optional else "missing-essential")
                if available is False
                else "unknown"
            )
        )
        matches.append(
            {
                "canonical_ingredient": name,
                "optional": optional,
                "status": status,
                "product_ids": product_ids if supported else [],
                "snapshot_id": evidence.get("snapshot_id") if evidence else None,
                "store_id": evidence.get("store_id") if evidence else None,
                "verified_at": evidence.get(
                    "last_verified_at", evidence.get("last_verified_timestamp")
                )
                if evidence
                else None,
                "substitution": None,
            }
        )
    essential = [row for row in matches if not row["optional"]]
    optional = [row for row in matches if row["optional"]]
    known = sum(row["status"] == "available" for row in matches)
    coverage = known / len(matches) if matches else 0
    ess_coverage = (
        sum(row["status"] == "available" for row in essential) / len(essential)
        if essential
        else coverage
    )
    opt_coverage = (
        sum(row["status"] == "available" for row in optional) / len(optional)
        if optional
        else ess_coverage
    )
    share = s["essential_availability_share"]
    foodlion = weights["foodlion"] * (share * ess_coverage + (1 - share) * opt_coverage)
    active = recipe.get("active_minutes")
    total = recipe.get("total_minutes")
    active_credit = (
        min(1, p["max_active_minutes"] / max(1, active))
        if isinstance(active, (int, float)) and active >= 0
        else s["unknown_evidence_credit"]
    )
    total_credit = (
        min(1, p["preferred_max_total_minutes"] / max(1, total))
        if isinstance(total, (int, float)) and total >= 0
        else s["unknown_evidence_credit"]
    )
    time = weights["time"] * (
        s["active_time_share"] * active_credit + (1 - s["active_time_share"]) * total_credit
    )
    entries = aliases.get("ingredients", {})
    protein = any(entries.get(name, {}).get("protein") for name in unique)
    vegetable = any(entries.get(name, {}).get("vegetable") for name in unique)
    nutrition_preferences = p["nutrition"]
    signals = [
        ("prefer_meaningful_protein_source", protein, s["protein_share"]),
        ("prefer_vegetables", vegetable, s["vegetables_share"]),
        ("prefer_balanced_meal", protein and vegetable, s["balance_share"]),
    ]
    enabled_weight = sum(weight for key, signal, weight in signals if nutrition_preferences[key])
    nutrition_credit = (
        sum(weight * bool(signal) for key, signal, weight in signals if nutrition_preferences[key])
        / enabled_weight
        if enabled_weight
        else 0
    )
    processed_fraction = sum(bool(entries.get(name, {}).get("processed")) for name in unique) / max(
        1, len(unique)
    )
    if (
        nutrition_preferences["penalize_highly_processed_food_heavy_meals"]
        and processed_fraction >= s["processed_fraction_threshold"]
    ):
        nutrition_credit *= 1 - s["processed_penalty"]
    nutrition = weights["nutrition"] * nutrition_credit
    ingredient_credit = falling(
        len(unique), s["simple_ingredient_count"], s["complex_ingredient_count"]
    )
    step_credit = (
        falling(len(recipe["instructions"]), s["simple_step_count"], s["complex_step_count"])
        if recipe["instructions"]
        else 0
    )
    pref = p["preferences"]
    methods = set(recipe.get("cooking_method", []))
    method_preferences = {
        "one-pan": "prefer_one_pan",
        "sheet-pan": "prefer_sheet_pan",
        "air fryer": "prefer_air_fryer",
        "oven": "prefer_simple_oven",
        "stovetop": "prefer_stovetop_simple",
    }
    bonuses = [bool(method in methods and pref[key]) for method, key in method_preferences.items()]
    low_cleanup = bool(methods & {"one-pan", "sheet-pan", "no-cook"}) and pref["prefer_low_cleanup"]
    batch = (
        isinstance(recipe.get("servings"), (int, float))
        and recipe["servings"] >= s["batch_servings"]
        and pref["prefer_batch_cooking"]
    )
    common = (
        sum(name in entries for name in unique) / max(1, len(unique))
        if pref["prefer_common_ingredients"]
        else 0
    )
    # Known canonical pantry ingredients are reusable proxies, not price/usage claims.
    reusable = (
        any(
            entries.get(name, {}).get("category") in {"pantry", "grain", "spice"} for name in unique
        )
        and pref["prefer_reusable_ingredients"]
    )
    method_credit = min(
        1,
        s["method_bonus"] * bool(any(bonuses) or low_cleanup or batch)
        + (1 - s["method_bonus"]) * (common + bool(reusable)) / 2,
    )
    simplicity = weights["simplicity"] * (
        s["simplicity_ingredient_share"] * ingredient_credit
        + s["simplicity_step_share"] * step_credit
        + s["simplicity_method_share"] * method_credit
    )
    missing_essential = [
        m["canonical_ingredient"] for m in essential if m["status"] == "missing-essential"
    ]
    missing_optional = [
        m["canonical_ingredient"] for m in optional if m["status"] == "missing-optional"
    ]
    unknown = [m["canonical_ingredient"] for m in matches if m["status"] == "unknown"]
    reasons = []
    if not unique:
        reasons.append("no parsed ingredients")
    if unknown:
        reasons.append("Food Lion availability unverified for one or more ingredients")
    if coverage < p["foodlion"]["minimum_ingredient_coverage"]:
        reasons.append("ingredient coverage below configured minimum")
    if len(missing_essential) > p["foodlion"]["max_missing_essential_ingredients"]:
        reasons.append("missing essential Food Lion ingredient")
    if len(missing_optional) > p["foodlion"]["max_missing_optional_ingredients"]:
        reasons.append("too many missing optional Food Lion ingredients")
    if active is None and p["require_known_active_time"]:
        reasons.append("active cooking time unknown")
    elif isinstance(active, (int, float)) and active > p["max_active_minutes"]:
        reasons.append("active cooking time exceeds preference")
    score = round(foodlion + time + nutrition + simplicity, 3)
    if score < p["minimum_approval_score"]:
        reasons.append("score below configured approval threshold")
    hard_failure = bool(
        missing_essential
        or missing_optional
        or (isinstance(active, (int, float)) and active > p["max_active_minutes"])
    )
    status = (
        "approved"
        if not reasons
        else ("needs-review" if unknown and not hard_failure else "rejected")
    )
    return {
        "recipe_id": recipe["id"],
        "foodlion_score": round(foodlion, 3),
        "time_score": round(time, 3),
        "nutrition_score": round(nutrition, 3),
        "simplicity_score": round(simplicity, 3),
        "total_score": score,
        "foodlion_coverage": round(coverage, 6),
        "total_ingredients": len(unique),
        "matched_ingredients": known,
        "missing_essential": missing_essential,
        "missing_optional": missing_optional,
        "unknown_ingredients": unknown,
        "ingredient_matches": matches,
        "status": status,
        "reasons": reasons or ["all configured approval gates passed"],
        "evidence": {
            "protein_ingredient_present": protein,
            "vegetable_ingredient_present": vegetable,
            "nutrition_method": "ingredient presence proxy; quantities and nutritional adequacy not established",
            "processed_ingredient_fraction": processed_fraction,
        },
        "input_fingerprint": stable_id(recipe, inventory, preferences, aliases, snapshot),
        "foodlion_snapshot": {
            key: snapshot.get(key)
            for key in ("snapshot_id", "snapshot_date", "completion_status", "configured_store")
        },
        "matcher_version": 1,
    }


def match_recipes(root):
    root = Path(root)
    inventory = sorted(
        read_jsonl(root / "data/foodlion/ingredients.jsonl"),
        key=lambda x: x.get("canonical_ingredient", x.get("name", "")),
    )
    preferences = load_yaml(root / "config/preferences.yaml")
    aliases = load_yaml(root / "config/ingredient-aliases.yaml")
    if sum(preferences["scoring"]["weights"].values()) != 100:
        raise ValueError("Scoring weights must total 100")
    latest_path = root / "state/foodlion/latest.json"
    snapshot = {}
    if latest_path.exists():
        latest = json.loads(latest_path.read_text())
        manifest_path = root / "snapshots/foodlion" / latest["snapshot_id"] / "manifest.json"
        if manifest_path.exists():
            snapshot = json.loads(manifest_path.read_text())
    rows = [
        evaluate(recipe, inventory, preferences, aliases, snapshot)
        for recipe in sorted(
            read_jsonl(root / "data/recipes/normalized/recipes.jsonl"), key=lambda x: x["id"]
        )
    ]
    write_jsonl(root / "data/matches/results.jsonl", rows)
    return rows
