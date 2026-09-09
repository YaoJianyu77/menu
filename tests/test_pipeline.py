import json
import shutil
from pathlib import Path

import pytest

from recipe_system.core import (
    Checkpoint,
    load_yaml,
    merge_shards,
    read_jsonl,
    validate_record,
    write_jsonl,
)
from recipe_system.match import evaluate, match_recipes
from recipe_system.normalize import (
    deduplicate,
    fingerprint,
    metric_text,
    normalize_ingredient,
    normalize_recipe,
    normalize_recipes,
)
from recipe_system.publish import build, publish

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def raw():
    return {
        "id": "fixture-recipe",
        "source_recipe_id": "test",
        "title": "Chicken and tomato skillet",
        "source": "test-only",
        "source_url": "https://example.test/recipe",
        "source_path": "recipe.md",
        "source_license": "CC0-1.0",
        "attribution": "Synthetic test fixture",
        "cuisine": "American",
        "servings": 4,
        "ingredients": ["200 g chicken breast", "2 roma tomatoes", "2 tbsp olive oil"],
        "instructions": [
            "Heat 2 tbsp olive oil in a skillet.",
            "Cook chicken and tomatoes until cooked through.",
        ],
        "timing": {"active_minutes": 10, "total_minutes": 20},
        "nutrition": None,
        "equipment": ["skillet"],
        "tags": [],
        "retrieved_at": "2026-09-08T12:00:00-04:00",
        "source_revision": "fixture",
        "publication_allowed": True,
    }


@pytest.fixture
def aliases():
    return load_yaml(ROOT / "config/ingredient-aliases.yaml")


@pytest.mark.parametrize(
    "source,quantity,unit",
    [
        ("2 tbsp olive oil", 30, "mL"),
        ("1 teaspoon salt", 5, "mL"),
        ("1 1/2 cups water", 360, "mL"),
        ("½ kg chicken", 0.5, "kg"),
        ("1½ tbsp oil", 22.5, "mL"),
        ("2 oz flour", 56.699, "g"),
    ],
)
def test_conversions(source, quantity, unit, aliases):
    item = normalize_ingredient(source, aliases)
    assert (item["quantity"], item["unit"]) == (quantity, unit)
    assert item["original_text"] == source


def test_alias_and_instructions(aliases):
    assert normalize_ingredient("2 roma tomatoes", aliases)["canonical_ingredient"] == "tomato"
    assert normalize_ingredient("30 mL EVOO", aliases)["canonical_ingredient"] == "olive oil"
    assert normalize_ingredient("2 tbsp soy sauce (optional)", aliases)["optional"]
    assert (
        metric_text("Bake at 350°F with 2 tablespoons oil") == "Bake at 176.667 °C with 30 mL oil"
    )


def test_fingerprint_stability(raw, aliases):
    recipe = normalize_recipe(raw, aliases)
    assert fingerprint(recipe) == fingerprint(json.loads(json.dumps(recipe)))
    recipe2 = {**recipe, "ingredients": list(reversed(recipe["ingredients"]))}
    assert fingerprint(recipe) == fingerprint(recipe2)
    recipe2 = {**recipe, "instructions": ["Bake instead."]}
    assert fingerprint(recipe) != fingerprint(recipe2)


def test_match_determinism_coverage_and_unknown(raw, aliases):
    recipe = normalize_recipe(raw, aliases)
    prefs = load_yaml(ROOT / "config/preferences.yaml")
    inventory = [
        {
            "canonical_ingredient": name,
            "currently_available": True,
            "product_ids": ["fixture-" + name],
            "snapshot_id": "fixture",
            "store_id": "fixture",
            "last_verified_at": "2026-09-08T12:00:00-04:00",
        }
        for name in ["chicken breast", "tomato", "olive oil"]
    ]
    snapshot = {"configured_store": {"store_id": "fixture"}}
    result = evaluate(recipe, inventory, prefs, aliases, snapshot)
    assert result == evaluate(recipe, inventory, prefs, aliases, snapshot)
    assert result["foodlion_coverage"] == 1
    assert result["status"] == "approved"
    partial = evaluate(recipe, inventory[:2], prefs, aliases, snapshot)
    assert partial["foodlion_coverage"] == 0.666667
    assert partial["unknown_ingredients"] == ["olive oil"]
    assert partial["status"] != "approved"
    empty = evaluate(recipe, [], prefs, aliases)
    assert empty["foodlion_score"] is None
    assert empty["foodlion_effective_weight"] == 0
    assert empty["status"] == "needs-review"
    assert empty["missing_essential"] == []


def test_checkpoint_and_merge(tmp_path):
    checkpoint = Checkpoint(tmp_path / "state.json", "agent-01")
    checkpoint.data["discovered"] = ["a", "b"]
    checkpoint.data["processed"] = ["a"]
    checkpoint.save()
    assert Checkpoint(tmp_path / "state.json", "agent-01").pending() == ["b"]
    with pytest.raises(ValueError):
        Checkpoint(tmp_path / "state.json", "agent-02")
    checkpoint.data["failures"]["b"] = {"reason": "fixture failure"}
    checkpoint.data["discovery_complete"] = True
    checkpoint.save()
    assert checkpoint.data["complete"]
    write_jsonl(tmp_path / "a.jsonl", [{"id": "1", "title": "x"}])
    merge_shards([tmp_path / "a.jsonl"], tmp_path / "merged.jsonl")
    before = (tmp_path / "merged.jsonl").read_bytes()
    merge_shards([tmp_path / "a.jsonl", tmp_path / "a.jsonl"], tmp_path / "merged.jsonl")
    assert before == (tmp_path / "merged.jsonl").read_bytes()


def test_end_to_end_fixture(tmp_path, raw):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    shutil.copytree(
        ROOT / "site", tmp_path / "site", ignore=shutil.ignore_patterns("dist", "content")
    )
    validate_record(raw, "raw-recipe")
    write_jsonl(tmp_path / "data/recipes/raw/fixture-agent.jsonl", [raw])
    assert normalize_recipes(tmp_path) == 1
    recipe = read_jsonl(tmp_path / "data/recipes/normalized/recipes.jsonl")[0]
    validate_record(recipe, "normalized-recipe")
    deduplicate(tmp_path)
    results = match_recipes(tmp_path)
    validate_record(results[0], "match")
    data = publish(tmp_path)
    assert len(data["recipes"]) == 1
    build(tmp_path)
    assert (tmp_path / "site/dist/index.html").exists()
    htmls = list((tmp_path / "site/dist").rglob("*.html"))
    assert len(htmls) >= 2
    from recipe_system.normalize import FORBIDDEN

    assert not any(FORBIDDEN.search(path.read_text()) for path in htmls)
    original = (tmp_path / "data/matches/results.jsonl").read_bytes()
    match_recipes(tmp_path)
    assert original == (tmp_path / "data/matches/results.jsonl").read_bytes()


def test_catalog_absence_is_not_explicit_stock_evidence(raw, aliases):
    recipe = normalize_recipe(raw, aliases)
    preferences = load_yaml(ROOT / "config/preferences.yaml")
    snapshot = {
        "snapshot_id": "fixture",
        "discovery_complete": True,
        "completion_status": "complete",
        "failures": [],
    }
    result = evaluate(recipe, [], preferences, aliases, snapshot)
    assert result["missing_essential"] == []
    assert sorted(result["unknown_ingredients"]) == ["chicken breast", "olive oil", "tomato"]
    assert result["status"] == "needs-review"


def test_cuisine_markup_and_trailing_metric_quantities(raw, aliases):
    raw["cuisine"] = '<a href="https://example.test">Italian</a>'
    assert normalize_recipe(raw, aliases)["cuisine"] == "Italian"
    item = normalize_ingredient("白砂糖 30 g", aliases)
    assert (item["canonical_ingredient"], item["quantity"], item["unit"]) == ("sugar", 30, "g")
    item = normalize_ingredient("2 tbsp [olive oil](https://example.test/oil)", aliases)
    assert (item["canonical_ingredient"], item["quantity"]) == ("olive oil", 30)


def test_schema_rejects_fabricated_availability_type():
    from jsonschema.exceptions import ValidationError

    with pytest.raises(ValidationError):
        validate_record(
            {
                "id": "x",
                "name": "fixture",
                "source_url": "https://example.test",
                "retrieved_at": "2026-09-08T12:00:00-04:00",
                "store_id": None,
                "availability": "probably in stock",
            },
            "product",
        )


def test_likely_catalog_and_unknown_are_not_store_stock(raw, aliases):
    recipe = normalize_recipe(raw, aliases)
    preferences = load_yaml(ROOT / "config/preferences.yaml")
    catalog = [
        {
            "canonical_ingredient": name,
            "status": "likely_available",
            "product_ids": ["catalog-" + name],
            "evidence": [
                {
                    "source_url": "https://foodlion.com/groceries/product/fixture/123",
                    "retrieved_at": "2026-09-09T00:00:00-04:00",
                    "store_specificity": "national_catalog",
                }
            ],
        }
        for name in ["chicken breast", "tomato", "olive oil"]
    ]
    likely = evaluate(recipe, catalog, preferences, aliases)
    unknown = evaluate(recipe, [], preferences, aliases)
    assert likely["verified_ingredient_count"] == 0
    assert likely["likely_ingredient_count"] == 3
    assert likely["status"] != "approved"
    assert unknown["foodlion_score"] is None
    assert unknown["score_denominator"] == 60
    assert unknown["total_score"] > 50
    assert unknown["missing_essential"] == []
    assert likely == evaluate(recipe, catalog, preferences, aliases)


def test_other_store_cannot_be_verified_for_configured_store(raw, aliases):
    recipe = normalize_recipe(raw, aliases)
    preferences = load_yaml(ROOT / "config/preferences.yaml")
    inventory = [
        {
            "canonical_ingredient": "tomato",
            "currently_available": True,
            "product_ids": ["actual-product"],
            "store_id": "other",
            "snapshot_id": "other-snapshot",
            "last_verified_at": "2026-09-09T00:00:00-04:00",
            "evidence": [
                {
                    "source_url": "https://foodlion.com/groceries/product/tomato/123",
                    "retrieved_at": "2026-09-09T00:00:00-04:00",
                    "store_id": "other",
                    "store_specificity": "specific_store",
                }
            ],
        }
    ]
    result = evaluate(
        recipe, inventory, preferences, aliases, {"configured_store": {"store_id": "configured"}}
    )
    assert result["verified_ingredient_count"] == 0
    assert result["likely_ingredient_count"] == 1
    unresolved_store = evaluate(recipe, inventory, preferences, aliases)
    assert unresolved_store["verified_ingredient_count"] == 0
    assert unresolved_store["likely_ingredient_count"] == 1


def test_dessert_and_condiment_cannot_be_recommended_as_meals(raw, aliases):
    preferences = load_yaml(ROOT / "config/preferences.yaml")
    for title in [
        "Chocolate Brownies",
        "Guacamole",
        "Citrus Vinaigrette",
        "Peanut Butter Frosting Recipe",
    ]:
        recipe = normalize_recipe({**raw, "title": title}, aliases)
        result = evaluate(recipe, [], preferences, aliases)
        assert result["status"] == "rejected"
        assert result["recommendation_status"] == "not-recommended"
        assert result["total_score"] < 40


def test_unknown_time_never_outscores_supported_fast_time(raw, aliases):
    preferences = load_yaml(ROOT / "config/preferences.yaml")
    recipe = normalize_recipe(raw, aliases)
    unknown = evaluate(
        {**recipe, "active_minutes": None, "total_minutes": None}, [], preferences, aliases
    )
    bounded = evaluate(
        {**recipe, "active_minutes": None, "total_minutes": 12}, [], preferences, aliases
    )
    assert bounded["active_time_evidence"] == "total-time-upper-bound"
    assert bounded["time_score"] > unknown["time_score"]
    assert bounded["total_score"] > unknown["total_score"]


def test_preparation_package_and_markdown_quantities(aliases):
    assert normalize_ingredient("**15** g olive oil", aliases)["quantity"] == 15
    assert (
        normalize_ingredient("1/4 tsp salt, (divided)", aliases)["canonical_ingredient"] == "salt"
    )
    package = normalize_ingredient("2 (15 oz) cans chickpeas, (drained and rinsed)", aliases)
    assert package["canonical_ingredient"] == "chickpea"
    assert package["package"]["count"] == 2
    assert package["package"]["unit"] == "g"
    assert package["quantity"] == 2  # package count, never invented drained mass


def test_explicit_timing_conflicts_and_storage_are_distinct():
    from recipe_system.normalize_quality import labelled_times, timing_consistency

    details, issues = timing_consistency(["Simmer for 40 minutes."], 20)
    assert details["step_time_lower_bound_minutes"] == 40
    assert issues
    assert timing_consistency(["Store leftovers for 3 days."], 20)[1] == []
    assert timing_consistency(["Make the pickles 2 days before cooking."], 20)[0][
        "requires_advance_preparation"
    ]
    assert labelled_times("Prep\n20 minutes\nTotal Time\n45 minutes")["total_minutes"] == 45
    assert "active_minutes" not in labelled_times("Prep\n20 minutes")


@pytest.mark.parametrize(
    "original,expected",
    [
        ("1 c. à soupe huile", "15 mL huile"),
        ("2 TL Salz", "10 mL Salz"),
        ("1 κ.σ. ελαιόλαδο", "15 mL ελαιόλαδο"),
        ("Cup4Cup flour", "Cup4Cup flour"),
    ],
)
def test_explicit_foreign_units_and_brand_boundaries(original, expected):
    assert metric_text(original) == expected


def test_chinese_equals_quantity_and_count(aliases):
    item = normalize_ingredient("鸡胸肉 = 300g", aliases)
    assert (item["canonical_ingredient"], item["quantity"], item["unit"]) == (
        "chicken breast",
        300,
        "g",
    )
    item = normalize_ingredient("大蒜 = 2瓣", aliases)
    assert item["canonical_ingredient"] == "garlic"
    assert item["quantity"] == 2
    assert item["count_unit"] == "瓣"


def test_container_count_not_weight_range(aliases):
    item = normalize_ingredient("2 – 16oz can dark kidney beans", aliases)
    assert item["quantity"] == 2
    assert item["quantity_max"] is None
    assert item["unit"] is None
    assert item["package"]["quantity"] == 453.592
    assert item["display"] == "2 (453.592 g) can dark kidney beans"
    assert metric_text("2-4 tbsp oil") == "30–60 mL oil"
    assert metric_text("1 1/2-tablespoon scoop") == "22.5 mL scoop"
    assert metric_text("Cup-4-Cup flour") == "Cup-4-Cup flour"
    assert metric_text("16-oz. mason jar") == "mason jar (check source capacity)"
    assert normalize_ingredient("16-oz. mason jar", aliases)["quantity"] is None
    assert metric_text("1 tbspbaking powder") == "15 mL baking powder"
    assert normalize_ingredient("6 fl. oz. water", aliases)["unit"] == "mL"
    assert normalize_ingredient("⅗ cup water", aliases)["quantity"] == 144


def test_package_sizes_affect_fingerprint(raw, aliases):
    raw["ingredients"] = ["2 (15 oz) cans chickpeas", "2 tomatoes"]
    first = normalize_recipe(raw, aliases)
    raw["ingredients"][0] = "2 (10 oz) cans chickpeas"
    assert fingerprint(first) != fingerprint(normalize_recipe(raw, aliases))


def test_dish_context_and_frequency_aggregate(raw, aliases):
    from recipe_system.meal_quality import meal_signals

    recipe = normalize_recipe(raw, aliases)
    recipe["title"] = "Tzatziki"
    assert meal_signals(recipe, aliases)["meal_role"] == "condiment"
    recipe["title"] = "Vegetables in Salsa Verde"
    assert meal_signals(recipe, aliases)["meal_role"] != "condiment"
    recipe["ingredients"] = [normalize_ingredient(f"ingredient _{n}_", aliases) for n in range(25)]
    assert (
        "ingredient frequency/category aggregate, not a recipe ingredient list"
        in meal_signals(recipe, aliases)["quality_issues"]
    )
