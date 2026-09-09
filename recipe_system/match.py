"""Explainable deterministic scoring. Unknown inventory never becomes availability."""

import json
from pathlib import Path
from urllib.parse import urlparse

from .core import load_yaml, read_jsonl, stable_id, write_jsonl
from .meal_quality import meal_signals


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
    snapshot = snapshot or {}
    p, s = preferences, preferences["scoring"]
    fl = p["foodlion"]
    weights = s["weights"]
    meal_rules = meal_rules or load_yaml(
        Path(__file__).resolve().parents[1] / "config/meal-rules.yaml"
    )
    quality = meal_signals(recipe, aliases, meal_rules)
    configured_store_id = (snapshot.get("configured_store") or {}).get("store_id")
    by_name = {}
    priority = {"unknown": 0, "likely_available": 1, "unavailable": 2, "verified_available": 3}
    for entry in inventory:
        name = entry.get("canonical_ingredient", entry.get("name"))
        if (
            priority[ingredient_evidence(entry, configured_store_id)[0]]
            > priority[ingredient_evidence(by_name.get(name), configured_store_id)[0]]
        ):
            by_name[name] = entry
    unique = {}
    for ingredient in recipe["ingredients"]:
        name = ingredient["canonical_ingredient"]
        if name:
            unique[name] = unique.get(name, True) and bool(ingredient.get("optional", False))
    matches = []
    for name, optional in sorted(unique.items()):
        entry = by_name.get(name) or {}
        status, evidence = ingredient_evidence(entry, configured_store_id)
        matches.append(
            {
                "canonical_ingredient": name,
                "optional": optional,
                "status": status,
                "product_ids": entry.get("product_ids", []) if status != "unknown" else [],
                "snapshot_id": entry.get("snapshot_id"),
                "store_id": entry.get("store_id"),
                "verified_at": entry.get("last_verified_at"),
                "observed_at": entry.get("last_observed_at") or entry.get("last_verified_at"),
                "evidence": evidence[:3],
                "evidence_count": len(evidence),
                "evidence_index": "data/foodlion/evidence/ingredients.jsonl" if evidence else None,
                "store_specificity": sorted(
                    {e.get("store_specificity", "unknown") for e in evidence}
                ),
                "substitution": None,
            }
        )
    essential = [m for m in matches if not m["optional"]]
    optional = [m for m in matches if m["optional"]]
    verified = sum(m["status"] == "verified_available" for m in matches)
    likely = sum(m["status"] == "likely_available" for m in matches)
    unavailable = sum(m["status"] == "unavailable" for m in matches)
    known = verified + likely
    coverage = known / max(1, len(matches))
    evidence_fraction = (known + unavailable) / max(1, len(matches))

    # Unknown weight is omitted, not assigned zero availability. The point score is
    # conditional on observed evidence; effective contribution scales with coverage.
    def coverage_parts(items):
        if not items:
            return 0, 0
        credit = sum(
            1
            if m["status"] == "verified_available"
            else fl.get("likely_score_credit", 0.85)
            if m["status"] == "likely_available"
            else 0
            for m in items
        ) / len(items)
        observed = sum(m["status"] != "unknown" for m in items) / len(items)
        return credit, observed

    ec, eo = coverage_parts(essential or matches)
    oc, oo = coverage_parts(optional or essential or matches)
    share = s["essential_availability_share"]
    available_credit = share * ec + (1 - share) * oc
    observed_weight = share * eo + (1 - share) * oo
    foodlion = weights["foodlion"] * available_credit / observed_weight if observed_weight else None
    effective_foodlion = weights["foodlion"] * available_credit
    active = recipe.get("active_minutes")
    total = recipe.get("total_minutes")
    active_credit = (
        min(1, p["max_active_minutes"] / max(1, active))
        if isinstance(active, (int, float)) and active >= 0
        else s["unknown_evidence_credit"]
    )
    active_bound_supported = (
        active is None and isinstance(total, (int, float)) and 0 < total <= p["max_active_minutes"]
    )
    if active_bound_supported:
        active_credit = 1
    total_credit = (
        min(1, p["preferred_max_total_minutes"] / max(1, total))
        if isinstance(total, (int, float)) and total >= 0
        else s["unknown_evidence_credit"]
    )
    time = weights["time"] * (
        s["active_time_share"] * active_credit + (1 - s["active_time_share"]) * total_credit
    )
    entries = aliases.get("ingredients", {})
    protein = bool(quality["protein_ingredients"])
    vegetable = bool(quality["vegetable_ingredients"])
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
    if quality["rich_ingredient_fraction"] >= meal_rules["rich_fraction_threshold"]:
        nutrition_credit *= meal_rules["rich_balance_multiplier"]
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
        m["canonical_ingredient"] for m in essential if m["status"] == "unavailable"
    ]
    missing_optional = [m["canonical_ingredient"] for m in optional if m["status"] == "unavailable"]
    unknown = [m["canonical_ingredient"] for m in matches if m["status"] == "unknown"]
    reasons, restrictions = [], []
    if unknown:
        reasons.append(
            "Food Lion evidence unknown for some ingredients; unobserved availability weight excluded"
        )
    if likely:
        reasons.append(
            "Food Lion catalog evidence supports likely availability, not configured-store stock"
        )
    if missing_essential:
        restrictions.append("explicit unavailable essential Food Lion ingredient")
    if len(missing_optional) > fl["max_missing_optional_ingredients"]:
        restrictions.append("too many explicitly unavailable optional Food Lion ingredients")
    if active_bound_supported:
        reasons.append(
            "active effort is bounded by explicit total time within the configured active-time budget"
        )
    elif active is None:
        reasons.append("active cooking time unknown; no active-time credit")
    elif active > p["max_active_minutes"]:
        restrictions.append("active cooking time exceeds preference")
    if total is None:
        reasons.append("total cooking time unknown; no total-time credit")
    if quality["meal_role"] in {"dessert", "condiment", "drink", "bread", "component", "side"}:
        restrictions.append("dish role is not an everyday complete meal: " + quality["meal_role"])
    if quality["quality_issues"]:
        restrictions.extend(quality["quality_issues"])
    quality_points = time + nutrition + simplicity
    denominator = (
        weights["time"]
        + weights["nutrition"]
        + weights["simplicity"]
        + weights["foodlion"] * observed_weight
    )
    score = 100 * (quality_points + effective_foodlion) / denominator
    adjustments = []
    if quality["meal_role"] in {"dessert", "condiment", "drink", "bread", "component", "side"}:
        score *= meal_rules["non_meal_score_multiplier"]
        adjustments.append(
            {"reason": "non-meal dish role", "multiplier": meal_rules["non_meal_score_multiplier"]}
        )
    if not (protein and vegetable):
        score *= meal_rules.get("no_meal_structure_multiplier", 0.8)
        adjustments.append(
            {
                "reason": "complete protein/vegetable structure not established",
                "multiplier": meal_rules.get("no_meal_structure_multiplier", 0.8),
            }
        )
    identity_multiplier = (
        1
        - meal_rules.get("unresolved_score_penalty", 0.5)
        * quality["unresolved_ingredient_fraction"]
    )
    score *= identity_multiplier
    if identity_multiplier < 1:
        adjustments.append(
            {
                "reason": "unresolved ingredient identities limit ranking confidence (independent of stock evidence)",
                "multiplier": identity_multiplier,
            }
        )
    if quality["quality_issues"]:
        score *= meal_rules["quality_failure_score_multiplier"]
        adjustments.append(
            {
                "reason": "extraction quality issues",
                "multiplier": meal_rules["quality_failure_score_multiplier"],
            }
        )
    if score < p["minimum_approval_score"]:
        reasons.append("score below configured approval threshold")
    strict = (
        not restrictions
        and score >= p["minimum_approval_score"]
        and verified / max(1, len(matches)) >= fl["minimum_ingredient_coverage"]
        and not any(m["status"] != "verified_available" for m in essential)
        and (active is not None or active_bound_supported or not p["require_known_active_time"])
    )
    recommendation = p.get("recommendations", {})
    candidate = (
        not restrictions
        and score >= recommendation.get("minimum_score", 65)
        and (total is not None or not recommendation.get("require_known_total_time", True))
        and (total is None or total <= p["preferred_max_total_minutes"])
        and (protein and vegetable or not recommendation.get("require_protein_and_vegetable", True))
        and quality["unresolved_ingredient_fraction"]
        <= meal_rules["maximum_unresolved_fraction_for_recommendation"]
        and len(unique) <= meal_rules["maximum_ingredients_for_recommendation"]
        and coverage >= recommendation.get("minimum_catalog_evidence_coverage", 0.5)
    )
    status = "approved" if strict else "rejected" if restrictions else "needs-review"
    recommendation_status = (
        "recommended" if strict else "recommended-with-caveats" if candidate else "not-recommended"
    )
    if candidate and not strict:
        reasons.append(
            "provisional recommendation: check active time and exact-store product availability"
        )
    return {
        "recipe_id": recipe["id"],
        "foodlion_score": round(foodlion, 3) if foodlion is not None else None,
        "foodlion_effective_points": round(effective_foodlion, 3),
        "foodlion_effective_weight": round(weights["foodlion"] * observed_weight, 3),
        "time_score": round(time, 3),
        "active_time_evidence": "explicit"
        if active is not None
        else "total-time-upper-bound"
        if active_bound_supported
        else "unknown",
        "nutrition_score": round(nutrition, 3),
        "simplicity_score": round(simplicity, 3),
        "total_score": round(score, 3),
        "score_denominator": round(denominator, 3),
        "score_adjustments": adjustments,
        "foodlion_coverage": round(coverage, 6),
        "foodlion_verified_coverage": round(verified / max(1, len(matches)), 6),
        "foodlion_evidence_coverage": round(evidence_fraction, 6),
        "foodlion_confidence": round(
            (verified + fl.get("likely_confidence_weight", 0.6) * likely) / max(1, len(matches)), 6
        ),
        "verified_ingredient_count": verified,
        "likely_ingredient_count": likely,
        "unknown_ingredient_count": len(unknown),
        "unsupported_ingredient_count": unavailable,
        "total_ingredients": len(unique),
        "matched_ingredients": known,
        "missing_essential": missing_essential,
        "missing_optional": missing_optional,
        "unknown_ingredients": unknown,
        "ingredient_matches": matches,
        "status": status,
        "recommendation_status": recommendation_status,
        "reasons": restrictions + reasons or ["all configured approval gates passed"],
        "quality": quality,
        "evidence": {
            "protein_ingredient_present": protein,
            "vegetable_ingredient_present": vegetable,
            "nutrition_method": "ingredient presence proxy; portions and nutritional adequacy not established",
            "processed_ingredient_fraction": processed_fraction,
        },
        "input_fingerprint": stable_id(
            recipe, inventory, preferences, aliases, snapshot, meal_rules
        ),
        "foodlion_snapshot": {
            key: snapshot.get(key)
            for key in ("snapshot_id", "snapshot_date", "completion_status", "configured_store")
        },
        "matcher_version": 2,
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
    write_jsonl(root / "data/matches/results.jsonl", rows)
    return rows
