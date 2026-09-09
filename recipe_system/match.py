"""Explainable deterministic scoring. Unknown inventory never becomes availability."""

import json
from pathlib import Path
from urllib.parse import urlparse

from .core import load_yaml, read_jsonl, stable_id, write_jsonl


def falling(value, good, bad):
    return max(0, min(1, (bad - value) / max(1, bad - good)))


def ingredient_evidence(entry, configured_store_id=None):
    """Evidence absence is never a stock assertion; other-store evidence stays qualified."""
    if not entry:
        return "unknown", []
    ids = entry.get("product_ids", [])
    records = entry.get("evidence", [])
    timestamp = entry.get("last_verified_at") or entry.get("last_observed_at")
    declared = entry.get("status")
    if not ids:
        return "unknown", records
    other_store = bool(entry.get("store_id") and entry["store_id"] != configured_store_id)
    other_store = other_store or entry.get("store_specificity") in {
        "other_store",
        "national_catalog",
    }
    credible = [
        e
        for e in records
        if e.get("retrieved_at")
        and (
            (urlparse(e.get("source_url", "")).hostname or "") == "foodlion.com"
            or (urlparse(e.get("source_url", "")).hostname or "").endswith(".foodlion.com")
        )
    ]
    scoped = (
        bool(
            configured_store_id
            and entry.get("store_id") == configured_store_id
            and entry.get("snapshot_id")
            and timestamp
        )
        and not other_store
    )
    if other_store and entry.get("currently_available") is True:
        return ("likely_available" if credible else "unknown"), records
    if entry.get("currently_available") is False and scoped:
        return "unavailable", records
    if entry.get("currently_available") is True and scoped:
        return "verified_available", records
    if declared == "verified_available" and any(
        e.get("store_specificity") in {"configured_store", "specific_store"}
        and e.get("store_id")
        and configured_store_id
        and e["store_id"] == configured_store_id
        for e in credible
    ):
        return "verified_available", records
    if declared in {"likely_available", "verified_available"} and credible:
        return "likely_available", records
    return "unknown", records


def evaluate(recipe, inventory, preferences, aliases, snapshot=None, meal_rules=None):
    """Catalog compatibility plus practical meal ranking; local stock is not a gate."""
    from .practical import practical_signals

    snapshot = snapshot or {}
    rules = meal_rules or load_yaml(Path(__file__).resolve().parents[1] / "config/meal-rules.yaml")
    p, fl = preferences["practical"], preferences["foodlion"]
    weights = preferences["scoring"]["weights"]
    quality = practical_signals(recipe, aliases, rules, preferences)
    by_name = {}
    for entry in inventory:
        name = entry.get("canonical_ingredient", entry.get("name"))
        previous = by_name.get(name)
        if previous is None or len(entry.get("evidence", [])) > len(previous.get("evidence", [])):
            by_name[name] = entry
    unique = {}
    for i in recipe["ingredients"]:
        if i["canonical_ingredient"]:
            unique[i["canonical_ingredient"]] = unique.get(
                i["canonical_ingredient"], True
            ) and bool(i.get("optional"))
    matches = []
    for name, optional in sorted(unique.items()):
        entry = by_name.get(name, {})
        status, evidence = ingredient_evidence(
            entry, (snapshot.get("configured_store") or {}).get("store_id")
        )
        catalog = status in {"verified_available", "likely_available"} or bool(
            entry.get("product_ids")
            and evidence
            and all(
                (
                    (urlparse(e.get("source_url", "")).hostname or "") == "foodlion.com"
                    or (urlparse(e.get("source_url", "")).hostname or "").endswith(".foodlion.com")
                )
                for e in evidence
            )
        )
        compatibility = (
            "yes" if catalog else "probably" if name in fl["pantry_basics"] else "unknown"
        )
        matches.append(
            {
                "canonical_ingredient": name,
                "optional": optional,
                "status": status,
                "compatibility_status": compatibility,
                "foodlion_compatible": compatibility != "unknown",
                "compatibility_basis": "Food Lion catalog product"
                if catalog
                else "common pantry basic; not a stock assertion"
                if compatibility == "probably"
                else "no mapped catalog evidence",
                "product_ids": entry.get("product_ids", []) if status != "unknown" else [],
                "evidence": evidence[:3],
                "evidence_count": len(evidence),
                "evidence_index": "data/foodlion/evidence/ingredients.jsonl" if evidence else None,
                "snapshot_id": entry.get("snapshot_id"),
                "store_id": entry.get("store_id"),
                "verified_at": entry.get("last_verified_at"),
                "observed_at": entry.get("last_observed_at"),
                "store_specificity": sorted(
                    {e.get("store_specificity", "unknown") for e in evidence}
                ),
                "substitution": None,
            }
        )
    required = [i for i in matches if not i["optional"]] or matches
    optional = [i for i in matches if i["optional"]]
    coverage = sum(i["foodlion_compatible"] for i in required) / max(1, len(required))

    def compatibility_credit(items):
        return sum(
            1 if i["foodlion_compatible"] else fl["unknown_compatibility_credit"] for i in items
        ) / max(1, len(items))

    optional_share = fl["optional_share"] if optional else 0
    foodlion = weights["foodlion"] * (
        (1 - optional_share) * compatibility_credit(required)
        + optional_share * compatibility_credit(optional)
    )
    unknown_names = {
        i["canonical_ingredient"] for i in matches if i["compatibility_status"] == "unknown"
    }
    unknown_main = sorted(
        {
            i["canonical_ingredient"]
            for i in recipe["ingredients"]
            if i["canonical_ingredient"] in unknown_names
            and not i.get("optional")
            and isinstance(i.get("quantity"), (int, float))
            and i.get("unit") in {"g", "kg"}
            and i["quantity"] * (1000 if i["unit"] == "kg" else 1) >= p["unknown_main_min_g"]
        }
    )
    if unknown_main:
        foodlion *= p["unknown_main_compatibility_multiplier"]
    active, total = recipe.get("active_minutes"), recipe.get("total_minutes")
    timing = recipe.get("timing_quality") or {}
    scored_total = (
        max(
            total or 0,
            timing.get("step_time_lower_bound_minutes") or 0,
            quality["instruction_time_lower_bound"],
        )
        or None
    )

    def band(value, bands, unknown):
        return (
            unknown
            if value is None
            else next((credit for limit, credit in bands if value <= limit), bands[-1][1])
        )

    active_credit = band(active, p["active_bands"], p["unknown_active_credit"])
    total_credit = band(scored_total, p["total_bands"], p["unknown_total_credit"])
    estimated_active = {
        "Easy": p["unknown_active_credit"],
        "Moderate": p["moderate_unknown_active_credit"],
        "Involved": 0.45,
    }[quality["effort_level"]]
    if active is None:
        active_credit = estimated_active
    if (
        active is None
        and scored_total is not None
        and scored_total <= preferences["max_active_minutes"]
    ) and quality["effort_level"] == "Easy":
        active_credit = 1
    time_credit = (
        p["active_time_share"] * active_credit + (1 - p["active_time_share"]) * total_credit
    )
    if active is None and scored_total is None:
        time_credit = min(p["both_unknown_credit"], estimated_active)
    if timing.get("requires_advance_preparation") or quality["advance_preparation"]:
        time_credit *= p["advance_preparation_multiplier"]
    time = weights["time"] * time_credit
    protein, vegetables, staple = (
        bool(quality[k])
        for k in ["protein_ingredients", "vegetable_ingredients", "staple_ingredients"]
    )
    aliases.get("ingredients", {})
    processed = quality["processed_ingredient_fraction"]
    nutrition_credit = (
        p["protein_share"] * protein
        + p["vegetable_share"] * vegetables
        + p["staple_share"] * staple
        + p["balanced_share"] * (protein and vegetables)
    )
    if processed >= p["processed_fraction_threshold"]:
        nutrition_credit *= 1 - p["processed_penalty"]
    if quality["rich_ingredient_fraction"] >= p["rich_fraction_threshold"]:
        nutrition_credit *= 1 - p["rich_penalty"]
    added_fat_ml = sum(
        i.get("quantity", 0) * (1000 if i.get("unit") == "L" else 1)
        for i in recipe["ingredients"]
        if i["canonical_ingredient"]
        in {"cooking oil", "vegetable oil", "olive oil", "coconut oil", "butter"}
        and i.get("unit") in {"mL", "L"}
        and isinstance(i.get("quantity"), (int, float))
    )
    servings = recipe.get("servings")
    prominent_fat = added_fat_ml >= p["prominent_added_fat_ml"] and (
        not isinstance(servings, (int, float))
        or servings <= 0
        or added_fat_ml / servings >= p["added_fat_ml_per_serving"]
    )
    if prominent_fat:
        nutrition_credit *= p["added_fat_proxy_multiplier"]
    nutrition = weights["nutrition"] * nutrition_credit
    ingredient_credit = falling(len(unique), p["simple_ingredients"], p["complex_ingredients"])
    step_credit = falling(
        max(len(recipe["instructions"]), quality["preparation_operations"]),
        p["simple_steps"],
        p["complex_steps"],
    )
    easy_cleanup = bool(
        set(quality["cooking_method"]) & {"one-pan", "one-pot", "sheet-pan", "air fryer", "no-cook"}
    )
    batch = (
        isinstance(recipe.get("servings"), (int, float))
        and recipe["servings"] >= preferences["scoring"]["batch_servings"]
    )
    cleanup_credit = 1 if easy_cleanup else max(0.3, 0.9 - 0.15 * quality["vessel_count"])
    simplicity = weights["simplicity"] * (
        0.4 * ingredient_credit
        + 0.35 * step_credit
        + 0.2 * cleanup_credit
        + 0.05 * (1 if batch else 0.5)
    )
    score = foodlion + time + nutrition + simplicity
    adjustments = []
    if not quality["everyday_eligible"]:
        cap = p["quality_score_cap"] if quality["structural_issues"] else p["non_meal_score_cap"]
        score = min(score, cap)
        adjustments.append(
            {
                "reason": "recipe text needs review"
                if quality["structural_issues"]
                else "not a complete everyday meal",
                "cap": cap,
            }
        )
    score = round(score, 3)
    score_band = next(
        label
        for cutoff, label in [
            (90, "Excellent"),
            (80, "Strong"),
            (70, "Good"),
            (60, "Usable"),
            (0, "Low priority"),
        ]
        if score >= cutoff
    )
    eligible = quality["everyday_eligible"]
    recommended = eligible and score >= preferences["recommendations"]["minimum_score"]
    reasons = []
    if unknown_main:
        reasons.append("Check the main ingredient choice for your Food Lion shop")
    if prominent_fat:
        reasons.append("Uses a substantial amount of added cooking fat")
    if coverage >= 0.85:
        reasons.append("Ingredients generally sold at Food Lion")
    elif coverage >= 0.7:
        reasons.append("Most ingredients fit a Food Lion shop")
    else:
        reasons.append("Some ingredient choices may need checking")
    if active is not None and active <= 15:
        reasons.append("At most 15 minutes of active work")
    elif total is not None and total <= 30:
        reasons.append("Ready within 30 minutes")
    elif active is None:
        reasons.append("Active time not listed; effort estimated from recipe steps")
    if protein and vegetables:
        reasons.append("Protein and vegetables")
    elif protein:
        reasons.append("Includes a protein source")
    if staple:
        reasons.append("Includes a staple food")
    if easy_cleanup:
        reasons.append("Simple cooking method and cleanup")
    if batch:
        reasons.append("Makes several servings")
    if timing.get("requires_advance_preparation") or quality["advance_preparation"]:
        reasons.append("Plan ahead for preparation or resting")
    if quality["structural_issues"]:
        reasons.append("Check the original recipe before cooking")
    verified = sum(i["status"] == "verified_available" for i in matches)
    likely = sum(i["status"] == "likely_available" for i in matches)
    unknown = [i["canonical_ingredient"] for i in matches if i["status"] == "unknown"]
    unavailable = sum(i["status"] == "unavailable" for i in matches)
    return {
        "recipe_id": recipe["id"],
        "foodlion_score": round(foodlion, 3),
        "foodlion_effective_points": round(foodlion, 3),
        "foodlion_effective_weight": weights["foodlion"],
        "time_score": round(time, 3),
        "nutrition_score": round(nutrition, 3),
        "simplicity_score": round(simplicity, 3),
        "total_score": score,
        "score_denominator": 100,
        "score_adjustments": adjustments,
        "active_time_evidence": "explicit"
        if active is not None
        else "total-time-upper-bound"
        if scored_total is not None and scored_total <= preferences["max_active_minutes"]
        else "estimated-effort",
        "scored_total_minutes": scored_total,
        "foodlion_coverage": round(coverage, 6),
        "foodlion_verified_coverage": round(verified / max(1, len(matches)), 6),
        "foodlion_evidence_coverage": round((verified + likely) / max(1, len(matches)), 6),
        "foodlion_confidence": round((verified + likely) / max(1, len(matches)), 6),
        "verified_ingredient_count": verified,
        "likely_ingredient_count": likely,
        "unknown_ingredient_count": len(unknown),
        "unsupported_ingredient_count": unavailable,
        "total_ingredients": len(matches),
        "required_ingredients": len(required),
        "matched_ingredients": sum(i["foodlion_compatible"] for i in required),
        "missing_essential": [],
        "missing_optional": [],
        "unknown_ingredients": unknown,
        "ingredient_matches": matches,
        "status": "approved" if recommended else "needs-review" if eligible else "rejected",
        "recommendation_status": "recommended" if recommended else "not-recommended",
        "everyday_eligible": eligible,
        "meal_type": quality["meal_type"],
        "effort_level": quality["effort_level"],
        "score_band": score_band,
        "cooking_method": quality["cooking_method"],
        "reasons": reasons,
        "quality": quality,
        "evidence": {
            "protein_ingredient_present": protein,
            "vegetable_ingredient_present": vegetables,
            "staple_ingredient_present": staple,
            "processed_ingredient_fraction": processed,
            "prominent_added_fat": prominent_fat,
            "unknown_main_ingredients": unknown_main,
            "nutrition_method": "ingredient structure; no calorie or macro estimates",
        },
        "input_fingerprint": stable_id(recipe, inventory, preferences, aliases, rules),
        "foodlion_snapshot": {
            key: snapshot.get(key)
            for key in ("snapshot_id", "snapshot_date", "completion_status", "configured_store")
        },
        "matcher_version": 3,
    }


def match_recipes(root):
    root = Path(root)
    inventory = sorted(
        read_jsonl(root / "data/foodlion/ingredients.jsonl")
        + read_jsonl(root / "data/foodlion/evidence/ingredients.jsonl"),
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
    rules_path = root / "config/meal-rules.yaml"
    rules = load_yaml(rules_path) if rules_path.exists() else None
    rows = [
        evaluate(recipe, inventory, preferences, aliases, snapshot, rules)
        for recipe in sorted(
            read_jsonl(root / "data/recipes/normalized/recipes.jsonl"), key=lambda x: x["id"]
        )
    ]
    groups = read_jsonl(root / "data/recipes/duplicates/groups.jsonl")
    membership = {rid: group for group in groups for rid in group["recipe_ids"]}
    for row in rows:
        group = membership.get(row["recipe_id"], {})
        row["duplicate_group"] = group.get("fingerprint")
        row["representative_id"] = group.get("representative_id", row["recipe_id"])
        row["ranking_representative"] = row["recipe_id"] == row["representative_id"]
        if not row["ranking_representative"] and row["recommendation_status"] != "not-recommended":
            row["recommendation_status"] = "duplicate-variant"
            row["reasons"].append(
                "exact duplicate retained; representative is used in recommendations"
            )
    recipes_by_id = {r["id"]: r for r in read_jsonl(root / "data/recipes/normalized/recipes.jsonl")}
    seen_titles = set()
    for row in sorted(rows, key=lambda r: (-r["total_score"], r["recipe_id"])):
        title = " ".join(recipes_by_id[row["recipe_id"]]["title"].casefold().split())
        row["discovery_representative"] = row["ranking_representative"] and title not in seen_titles
        if row["ranking_representative"]:
            seen_titles.add(title)
    write_jsonl(root / "data/matches/results.jsonl", rows)
    return rows
