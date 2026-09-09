"""Regression cases discovered in an independent pipeline review."""

from pathlib import Path

import pytest

from recipe_system.core import load_yaml
from recipe_system.match import evaluate
from recipe_system.normalize import canonicalize, metric_text, normalize_ingredient

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "source,expected",
    [(".5 tbsp olive oil", "7.5 mL olive oil"), (".25 teaspoon salt", "1.25 mL salt")],
)
def test_leading_decimal_metric_quantity(source, expected):
    assert metric_text(source) == expected
    ingredient = normalize_ingredient(source, {"ingredients": {}})
    assert ingredient["quantity"] == float(expected.split()[0])
    assert ingredient["unit"] == "mL"
    assert ingredient["original_text"] == source


def test_fahrenheit_shorthand_is_converted():
    assert metric_text("Bake at 350F.") == "Bake at 176.667 °C."


def test_available_claim_requires_verification_timestamp():
    aliases = load_yaml(ROOT / "config/ingredient-aliases.yaml")
    preferences = load_yaml(ROOT / "config/preferences.yaml")
    recipe = {
        "id": "edge-case-fixture",
        "ingredients": [
            {"canonical_ingredient": name, "optional": False}
            for name in ["chicken breast", "tomato"]
        ],
        "instructions": ["Cook the fixture."],
        "active_minutes": 10,
        "total_minutes": 20,
        "servings": 4,
        "cooking_method": ["one-pan"],
    }
    inventory = [
        {
            "canonical_ingredient": name,
            "currently_available": True,
            "product_ids": ["fixture-" + name],
            "snapshot_id": "fixture-snapshot",
            "store_id": "fixture-store",
        }
        for name in ["chicken breast", "tomato"]
    ]
    result = evaluate(recipe, inventory, preferences, aliases)
    assert result["status"] != "approved"
    assert result["matched_ingredients"] == 0
    assert all(item["status"] == "unknown" for item in result["ingredient_matches"])


def test_unknown_inventory_does_not_become_missing_essential():
    aliases = load_yaml(ROOT / "config/ingredient-aliases.yaml")
    preferences = load_yaml(ROOT / "config/preferences.yaml")
    recipe = {
        "id": "unknown-fixture",
        "ingredients": [{"canonical_ingredient": "tomato", "optional": False}],
        "instructions": ["Cook fixture."],
        "active_minutes": None,
        "total_minutes": None,
    }
    result = evaluate(recipe, [], preferences, aliases)
    assert result["missing_essential"] == []
    assert result["unknown_ingredients"] == ["tomato"]
    assert result["foodlion_score"] is None
    assert result["foodlion_effective_weight"] == 0


def test_distinct_chicken_cuts_are_not_silent_availability_substitutions():
    aliases = load_yaml(ROOT / "config/ingredient-aliases.yaml")
    assert canonicalize("whole chicken", aliases) != canonicalize("chicken thighs", aliases)
    assert canonicalize("chicken drumsticks", aliases) != canonicalize("chicken thighs", aliases)


def test_unicode_fraction_slash_converts_entire_quantity():
    original = "1⁄2 cup milk"
    assert metric_text(original) == "120 mL milk"
    ingredient = normalize_ingredient(original, {"ingredients": {}})
    assert ingredient["quantity"] == 120
    assert ingredient["unit"] == "mL"
    assert ingredient["original_text"] == original


def test_decimal_comma_never_partially_converts_quantity():
    # Decimal commas occur in European sources. Preserve or correctly convert;
    # never convert only the 5 and turn 1.5 measures into 1,75 mL.
    original = "1,5 tbsp oil"
    assert metric_text(original) != "1,75 mL oil"


def test_adjacent_chinese_metric_unit_is_not_part_of_ingredient():
    ingredient = normalize_ingredient("100克鸡肉", {"ingredients": {}})
    assert ingredient["quantity"] == 100
    assert ingredient["unit"] == "g"
    assert ingredient["canonical_ingredient"] == "鸡肉"


def test_jsonl_embedded_unicode_line_separator_is_not_a_record_boundary(tmp_path):
    from recipe_system.core import read_jsonl, write_jsonl

    records = [{"id": "fixture", "text": "before\u2028after\u2029end"}]
    path = tmp_path / "unicode.jsonl"
    write_jsonl(path, records)
    assert read_jsonl(path) == records


@pytest.mark.parametrize("identity", ["ChatGPT-User", "GPTBot", "OAI-SearchBot"])
def test_custom_user_agent_cannot_override_relevant_robots_denial(identity):
    from recipe_system.foodlion import AccessBlocked, RespectfulClient

    class FakeClient(RespectfulClient):
        def _request(self, url):
            assert url.endswith("/robots.txt"), "Denied recipe page must never be requested"
            return f"User-agent: *\nAllow: /\n\nUser-agent: {identity}\nDisallow: /\n"

    with pytest.raises(AccessBlocked, match=identity):
        FakeClient(interval=0).get("https://example.test/recipes/one")


def test_redirect_never_follows_unchecked_destination():
    import urllib.request

    from recipe_system.foodlion import AccessBlocked, RefuseRedirects

    with pytest.raises(AccessBlocked, match="target not requested"):
        RefuseRedirects().redirect_request(
            urllib.request.Request("https://example.test/recipe"),
            None,
            302,
            "Found",
            {},
            "https://restricted.example/recipe",
        )


def test_explicit_null_product_availability_stays_unknown():
    from recipe_system.foodlion import product_record

    row = product_record(
        {"name": "Fixture tomato", "offers": {"availability": None}},
        "https://example.test/tomato",
        {"store_id": "fixture"},
        "2026-09-08T12:00:00-04:00",
        "fixture-snapshot",
    )
    assert row["availability"] is None
