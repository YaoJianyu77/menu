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
    result = evaluate(recipe, inventory, prefs, aliases)
    assert result == evaluate(recipe, inventory, prefs, aliases)
    assert result["foodlion_coverage"] == 1
    assert result["status"] == "approved"
    partial = evaluate(recipe, inventory[:2], prefs, aliases)
    assert partial["foodlion_coverage"] == 0.666667
    assert partial["unknown_ingredients"] == ["olive oil"]
    assert partial["status"] != "approved"
    empty = evaluate(recipe, [], prefs, aliases)
    assert empty["foodlion_score"] == 0
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


def test_complete_snapshot_absence_is_missing(raw, aliases):
    recipe = normalize_recipe(raw, aliases)
    preferences = load_yaml(ROOT / "config/preferences.yaml")
    snapshot = {
        "snapshot_id": "fixture",
        "discovery_complete": True,
        "completion_status": "complete",
        "failures": [],
    }
    result = evaluate(recipe, [], preferences, aliases, snapshot)
    assert sorted(result["missing_essential"]) == ["chicken breast", "olive oil", "tomato"]
    assert result["unknown_ingredients"] == []
    assert result["status"] == "rejected"


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
