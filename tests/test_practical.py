from pathlib import Path

from recipe_system.core import load_yaml
from recipe_system.match import evaluate

ROOT = Path(__file__).resolve().parents[1]


def meal(title="Chicken rice bowl", ingredients=None, instructions=None, **extra):
    names = ingredients or ["chicken breast", "tomato", "rice", "salt"]
    return {
        "id": "practical-fixture",
        "title": title,
        "ingredients": [
            {"canonical_ingredient": n, "optional": False, "original_text": n} for n in names
        ],
        "instructions": instructions or ["Mix chicken, rice and tomato."],
        "active_minutes": None,
        "total_minutes": None,
        "quality_issues": [],
        **extra,
    }


def score(recipe, inventory=None, snapshot=None):
    aliases = load_yaml(ROOT / "config/ingredient-aliases.yaml")
    prefs = load_yaml(ROOT / "config/preferences.yaml")
    if inventory is None:
        inventory = [
            {
                "canonical_ingredient": i["canonical_ingredient"],
                "status": "likely_available",
                "product_ids": ["catalog-fixture"],
                "evidence": [
                    {
                        "source_url": "https://foodlion.com/groceries/product/fixture/123",
                        "retrieved_at": "2026-09-09T10:00:00-04:00",
                        "store_specificity": "national_catalog",
                    }
                ],
            }
            for i in recipe["ingredients"]
        ]
    return evaluate(recipe, inventory, prefs, aliases, snapshot)


def test_catalog_approves_without_store_or_metadata():
    r = meal()
    a = score(r)
    b = score(r, snapshot={"configured_store": {"store_id": "unrelated-store"}})
    assert a["status"] == "approved"
    assert a["foodlion_score"] == 35
    assert a["total_score"] == b["total_score"]
    assert a["verified_ingredient_count"] == 0
    assert all(i["compatibility_status"] == "yes" for i in a["ingredient_matches"])
    assert r["active_minutes"] is None and r["total_minutes"] is None
    assert a["time_score"] > 15


def test_optional_garnish_and_pantry_are_soft():
    r = meal(ingredients=["chicken breast", "tomato", "salt", "water"])
    inventory = [
        {
            "canonical_ingredient": n,
            "status": "likely_available",
            "product_ids": ["product"],
            "evidence": [
                {
                    "source_url": "https://foodlion.com/groceries/product/fixture/123",
                    "retrieved_at": "2026-09-09T10:00:00-04:00",
                }
            ],
        }
        for n in ["chicken breast", "tomato"]
    ]
    before = score(r, inventory)
    r["ingredients"].append({"canonical_ingredient": "unmapped garnish", "optional": True})
    after = score(r, inventory)
    assert before["foodlion_coverage"] == after["foodlion_coverage"] == 1
    assert before["foodlion_score"] - after["foodlion_score"] < 2
    assert (
        next(i for i in after["ingredient_matches"] if i["canonical_ingredient"] == "water")[
            "compatibility_status"
        ]
        == "probably"
    )


def test_unknown_times_not_disqualified_but_fast_is_better():
    unknown = score(meal())
    fast = score(meal(active_minutes=10, total_minutes=20))
    oven = score(meal(active_minutes=10, total_minutes=45, cooking_method=["oven"]))
    assert unknown["everyday_eligible"] and unknown["status"] == "approved"
    assert unknown["time_score"] < fast["time_score"]
    assert oven["time_score"] > 23


def test_dessert_structure_and_dessert_precedence():
    for title in ["123456", "Chocolate Sandwich Cookies", "Fresh Fruit Pizza", "Snickerdoodles"]:
        r = meal(title, ingredients=["flour", "sugar", "egg", "butter", "vanilla extract"])
        result = score(r)
        assert result["meal_type"] == "Dessert"
        assert not result["everyday_eligible"]
        assert result["total_score"] < 60


def test_bread_and_cheese_in_complete_meal_are_not_unhealthy():
    r = meal("Chicken sandwich", ingredients=["chicken breast", "bread", "cheddar", "tomato"])
    result = score(r)
    assert result["everyday_eligible"]
    assert result["meal_type"] == "Sandwich"
    assert result["nutrition_score"] == 25


def test_filled_fried_food_and_advance_preparation_have_lower_convenience():
    simple = score(meal())
    involved = score(
        meal(
            instructions=[
                "Knead dough, roll up each filled parcel and deep-fry in batches. Refrigerate overnight."
            ]
        )
    )
    assert involved["effort_level"] == "Involved"
    assert involved["quality"]["advance_preparation"]
    assert involved["time_score"] < simple["time_score"]
    assert involved["everyday_eligible"]


def test_actual_corrupt_recipe_is_distinct_from_unknown_metadata():
    result = score(meal(quality_issues=["source body could not be confidently re-extracted"]))
    assert not result["everyday_eligible"]
    assert result["total_score"] <= 39


def test_savory_sweet_title_is_not_a_dessert():
    result = score(
        meal(
            "Sheet Pan Chicken and Sweet Potatoes",
            ingredients=["chicken thigh", "sweet potato", "olive oil"],
        )
    )
    assert result["everyday_eligible"]
    assert result["meal_type"] != "Dessert"


def test_chinese_dough_work_is_not_low_effort():
    result = score(meal(instructions=["揉面，然后把面团擀成薄片，包入馅料。"]))
    assert result["effort_level"] == "Involved"
    assert result["everyday_eligible"]


def test_unknown_main_ingredient_affects_shopping_confidence_not_eligibility():
    recipe = meal()
    recipe["ingredients"].append(
        {"canonical_ingredient": "unmapped food", "optional": False, "quantity": 1, "unit": "g"}
    )
    inventory = [
        {
            "canonical_ingredient": n,
            "status": "likely_available",
            "product_ids": ["product"],
            "evidence": [
                {
                    "source_url": "https://foodlion.com/groceries/product/fixture/123",
                    "retrieved_at": "2026-09-09T10:00:00-04:00",
                }
            ],
        }
        for n in ["chicken breast", "tomato", "rice", "salt"]
    ]
    small = score(recipe, inventory)
    recipe["ingredients"][-1]["quantity"] = 200
    main = score(recipe, inventory)
    assert main["foodlion_coverage"] == small["foodlion_coverage"]
    assert main["foodlion_score"] < small["foodlion_score"]
    assert main["everyday_eligible"]


def test_large_batch_oil_is_not_assumed_high_per_serving():
    recipe = meal(servings=10)
    recipe["ingredients"].append(
        {"canonical_ingredient": "olive oil", "optional": False, "quantity": 100, "unit": "mL"}
    )
    batch = score(recipe)
    recipe["servings"] = 2
    small = score(recipe)
    assert not batch["evidence"]["prominent_added_fat"]
    assert small["evidence"]["prominent_added_fat"]
    assert batch["nutrition_score"] > small["nutrition_score"]
