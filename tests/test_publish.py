"""Publication protects source prose and builds usable offline pages."""

import json
import shutil
from pathlib import Path

from recipe_system.core import atomic_json, write_jsonl
from recipe_system.publish import FORBIDDEN, build, publish


def prepare(tmp_path, allowed=False):
    (tmp_path / "site").mkdir()
    for name in ("app.js", "style.css"):
        shutil.copyfile(Path(__file__).parents[1] / "site" / name, tmp_path / "site" / name)
    write_jsonl(
        tmp_path / "data/recipes/normalized/recipes.jsonl",
        [
            {
                "id": "test",
                "title": "Tomato skillet",
                "cuisine": "American",
                "ingredients": [
                    {
                        "canonical_ingredient": "olive oil",
                        "quantity": 30,
                        "unit": "mL",
                        "original_text": "2 tbsp olive oil",
                    }
                ],
                "instructions": ["Add 2 tablespoons of oil and cook."],
                "publication_allowed": allowed,
                "source_url": "https://example.com/recipe",
                "source": "Example",
                "source_license": "unknown",
                "raw_id": "raw-test",
                "active_minutes": None,
                "total_minutes": 20,
                "cooking_method": ["stovetop"],
                "major_protein": None,
            }
        ],
    )
    write_jsonl(
        tmp_path / "data/matches/results.jsonl",
        [
            {
                "recipe_id": "test",
                "status": "rejected",
                "total_score": 20,
                "foodlion_coverage": None,
                "reasons": ["Inventory unknown"],
                "ingredient_matches": [{"canonical_ingredient": "olive oil", "status": "unknown"}],
            }
        ],
    )
    atomic_json(tmp_path / "data/personal/recipes.json", {"test": {"favorite": True}})


def test_publication_redacts_restricted_prose_and_raw_fields(tmp_path):
    prepare(tmp_path)
    first = publish(tmp_path)
    assert first == publish(tmp_path)
    row = first["recipes"][0]
    assert row["instructions"] == []
    assert "original_text" not in row["ingredients"][0]
    assert row["raw_id"] == "raw-test"
    assert row["source_url"] == "https://example.com/recipe"
    assert row["personal"]["favorite"] is True
    assert row["match"]["foodlion_coverage"] is None
    assert not FORBIDDEN.search(json.dumps(first))


def test_build_generates_offline_browse_and_recipe_pages(tmp_path):
    prepare(tmp_path, allowed=True)
    publish(tmp_path)
    result = build(tmp_path)
    assert result["recipe_detail_pages"] == 1
    assert result["pages"] == 2
    index = (tmp_path / "site/dist/index.html").read_text()
    recipe = (tmp_path / "site/dist/recipes/test.html").read_text()
    catalog = (tmp_path / "site/dist/index.html").read_text()
    for field in (
        "cuisine",
        "meal_type",
        "time",
        "protein",
        "method",
        "coverage",
    ):
        assert f'data-catalog-filter="{field}"' in catalog
    assert "My Recipes" in index
    assert "30 mL" in recipe
    assert "raw-test" not in recipe
    assert "Unknown" in recipe
    assert 'id="personal-form"' in recipe
    assert "https://example.com/recipe" in recipe
    assert "original_text" not in recipe
    for page in (tmp_path / "site/dist").rglob("*.html"):
        assert not FORBIDDEN.search(page.read_text())
    first = recipe
    build(tmp_path)
    assert (tmp_path / "site/dist/recipes/test.html").read_text() == first


def test_untrusted_title_and_source_link_are_escaped(tmp_path):
    prepare(tmp_path)
    data = publish(tmp_path)
    data["recipes"][0]["title"] = '<script>alert("x")</script>'
    data["recipes"][0]["source_url"] = "javascript:alert(1)"
    atomic_json(tmp_path / "site/content/recipes.json", data)
    build(tmp_path)
    page = (tmp_path / "site/dist/recipes/test.html").read_text()
    assert '<script>alert("x")</script>' not in page
    assert "javascript:alert" not in page


def test_source_urls_are_immutable_even_when_containing_measure_words(tmp_path):
    prepare(tmp_path)
    from recipe_system.core import read_jsonl
    from recipe_system.publish import visible_text

    path = tmp_path / "data/recipes/normalized/recipes.jsonl"
    rows = read_jsonl(path)
    original = "https://www.tablespoon.com/recipes/tbsp-test"
    collected = "https://github.com/example/recipes/blob/revision/tablespoon.md"
    rows[0]["original_source_url"] = original
    rows[0]["source_url"] = collected
    write_jsonl(path, rows)
    published = publish(tmp_path)["recipes"][0]
    assert published["source_url"] == collected
    assert published["original_source_url"] == original
    build(tmp_path)
    page = (tmp_path / "site/dist/recipes/test.html").read_text()
    assert f'href="{original}"' in page
    assert f'href="{collected}"' in page
    assert not FORBIDDEN.search(visible_text(page))


def test_catalog_compatibility_states_are_visible(tmp_path):
    prepare(tmp_path)
    data = publish(tmp_path)
    row = data["recipes"][0]
    row["ingredients"] += [
        {"canonical_ingredient": "salt"},
        {"canonical_ingredient": "tomato"},
    ]
    row["match"].update(
        recommendation_status="recommended-with-caveats",
        foodlion_score=None,
        foodlion_coverage=0.67,
        foodlion_verified_coverage=0,
        verified_ingredient_count=0,
        likely_ingredient_count=2,
        unknown_ingredient_count=1,
        unsupported_ingredient_count=0,
        score_denominator=60,
        ingredient_matches=[
            {"canonical_ingredient": "olive oil", "status": "likely_available"},
            {
                "canonical_ingredient": "salt",
                "status": "unknown",
                "compatibility_status": "probably",
            },
            {"canonical_ingredient": "tomato", "status": "verified_available"},
        ],
    )
    atomic_json(tmp_path / "site/content/recipes.json", data)
    build(tmp_path)
    page = (tmp_path / "site/dist/recipes/test.html").read_text()
    assert "Food Lion: Yes" in page
    assert "Food Lion: Probably" in page
    assert "Verified store coverage" not in page
    assert "Food Lion compatibility" in page
    assert "Local stock may vary." in page
    assert "Provisional recommendation" not in page
    assert "assessed weight points" not in page


def test_variant_control_preserves_access_to_all_records(tmp_path):
    prepare(tmp_path)
    data = publish(tmp_path)
    data["recipes"][0]["match"]["ranking_representative"] = False
    atomic_json(tmp_path / "site/content/recipes.json", data)
    build(tmp_path)
    page = (tmp_path / "site/dist/index.html").read_text()
    catalog = (tmp_path / "site/dist/index.html").read_text()
    assert "My Recipes" in page
    assert 'href="recipes/test.html"' in catalog


def test_package_and_count_display_preserves_cooking_facts(tmp_path):
    prepare(tmp_path)
    from recipe_system.core import read_jsonl

    path = tmp_path / "data/recipes/normalized/recipes.jsonl"
    rows = read_jsonl(path)
    rows[0]["ingredients"] = [
        {
            "canonical_ingredient": "chickpea",
            "quantity": 2,
            "display": "2 (425 g) cans chickpeas, drained",
            "count_unit": "cans",
            "package": {"count": 2, "quantity": 425, "unit": "g", "container": "can"},
            "original_text": "2 (15 oz) cans chickpeas, drained",
        }
    ]
    rows[0]["quality_issues"] = ["ingredient table contains an unresolved row"]
    write_jsonl(path, rows)
    data = publish(tmp_path)
    ingredient = data["recipes"][0]["ingredients"][0]
    assert ingredient["package"]["quantity"] == 425
    assert ingredient["count_unit"] == "cans"
    assert "original_text" not in ingredient
    build(tmp_path)
    page = (tmp_path / "site/dist/recipes/test.html").read_text()
    assert "2 (425 g) cans chickpeas, drained" in page
    assert "Some recipe details need checking" in page
    assert "ingredient table contains an unresolved row" not in page
    assert "15 oz" not in page


def test_homepage_focuses_on_meals_without_collection_jargon(tmp_path):
    prepare(tmp_path)
    data = publish(tmp_path)
    row = data["recipes"][0]
    row["match"].update(
        meal_type="Full meal",
        everyday_eligible=True,
        effort_level="Easy",
        score_band="Good",
        total_score=72,
    )
    row["categories"]["meal-type"] = ["Full meal"]
    atomic_json(tmp_path / "site/content/recipes.json", data)
    build(tmp_path)
    page = (tmp_path / "site/dist/index.html").read_text()
    for label in ("My Recipes", "Search recipes", "Cuisine", "Cooking Method", "Clear filters"):
        assert label in page
    assert "Full meal" in page
    assert "72/100" not in page
    for jargon in ("shard", "parser", "completion", "catalog IDs", "verified at the store"):
        assert jargon not in page
    assert "collections" not in data


def test_discovery_variant_remains_on_homepage(tmp_path):
    prepare(tmp_path)
    data = publish(tmp_path)
    data["recipes"][0]["match"].update(
        ranking_representative=True, discovery_representative=False, everyday_eligible=True
    )
    atomic_json(tmp_path / "site/content/recipes.json", data)
    build(tmp_path)
    page = (tmp_path / "site/dist/index.html").read_text()
    assert 'href="recipes/test.html"' in page
    catalog = (tmp_path / "site/dist/index.html").read_text()
    assert 'href="recipes/test.html"' in catalog
    assert data["recipes"][0]["match"]["ranking_representative"] is True
