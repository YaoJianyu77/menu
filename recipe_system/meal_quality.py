"""Deterministic dish-role and extraction-quality signals; no nutrient invention."""

import re
from pathlib import Path

from .core import load_yaml


def meal_signals(recipe, aliases, rules=None):
    rules = rules or load_yaml(Path(__file__).resolve().parents[1] / "config/meal-rules.yaml")
    title = recipe.get("title", "")
    tags = " ".join(str(t) for t in recipe.get("tags", []))
    role, evidence = "unknown", []
    exception = re.search(rules["meal_exceptions"], title)
    for candidate, pattern in rules["roles"].items():
        if re.search(pattern, title) and not exception:
            role, evidence = candidate, ["title matches configured dish-role pattern"]
            break
    if role == "unknown":
        for candidate in ["dessert", "condiment", "drink"]:
            if re.search(rf"\b{candidate}\b", tags, re.IGNORECASE):
                role, evidence = candidate, ["explicit source tag"]
                break
    names = {
        i["canonical_ingredient"]
        for i in recipe.get("ingredients", [])
        if i["canonical_ingredient"]
    }
    entries = aliases.get("ingredients", {})
    proteins = sorted(n for n in names if entries.get(n, {}).get("protein"))
    vegetables = sorted(n for n in names if entries.get(n, {}).get("vegetable"))
    if role == "unknown" and proteins and vegetables:
        role, evidence = (
            "meal_candidate",
            ["protein and vegetable ingredient presence; portions unverified"],
        )
    unresolved = sum(n not in entries for n in names) / max(1, len(names))
    issues = list(recipe.get("quality_issues", []))
    if len(names) < rules["minimum_meaningful_ingredients"]:
        issues.append("too few meaningful parsed ingredients")
    raw_ingredients = recipe.get("ingredients", [])
    frequency_rows = sum(
        bool(re.search(r"[A-Za-z]\s+_?\d+_?$", i.get("original_text", "")))
        and i.get("quantity") is None
        for i in raw_ingredients
    )
    if len(raw_ingredients) >= 20 and frequency_rows / len(raw_ingredients) > 0.7:
        issues.append("ingredient frequency/category aggregate, not a recipe ingredient list")
    if not recipe.get("instructions"):
        issues.append("no parsed instructions")
    return {
        "meal_role": role,
        "meal_role_evidence": evidence,
        "protein_ingredients": proteins,
        "vegetable_ingredients": vegetables,
        "unresolved_ingredient_fraction": round(unresolved, 6),
        "rich_ingredient_fraction": sum(n in rules["rich_ingredients"] for n in names)
        / max(1, len(names)),
        "quality_issues": sorted(set(issues)),
        "rules_version": rules["version"],
    }
