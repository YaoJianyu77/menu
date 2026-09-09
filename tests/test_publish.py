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
    assert result["pages"] == 2
    index = (tmp_path / "site/dist/index.html").read_text()
    recipe = (tmp_path / "site/dist/recipes/test.html").read_text()
    for field in ("cuisine", "status", "total", "active", "protein", "method", "coverage"):
        assert f'data-filter="{field}"' in index
    assert "30 mL" in recipe
    assert "raw-test" in recipe
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
