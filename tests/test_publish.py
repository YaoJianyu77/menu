"""Publication protects source prose and builds usable offline pages."""

import json
import shutil
from pathlib import Path

from recipe_system.core import atomic_json, write_jsonl
from recipe_system.publish import FORBIDDEN, publish


def prepare(tmp_path, allowed=False):
    (tmp_path / "site").mkdir()
    for name in ("hidden.js", "style.css"):
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


def test_publishing_retains_original_urls_and_provenance(tmp_path):
    prepare(tmp_path)
    from recipe_system.core import read_jsonl

    path = tmp_path / "data/recipes/normalized/recipes.jsonl"
    rows = read_jsonl(path)
    rows[0]["original_source_url"] = "https://www.tablespoon.com/recipes/tbsp-test"
    write_jsonl(path, rows)
    before = path.read_bytes()
    data = publish(tmp_path)
    assert data["recipes"][0]["original_source_url"] == rows[0]["original_source_url"]
    assert data["recipes"][0]["url"] == "recipes/test.html"
    assert data["recipes"][0]["raw_id"] == "raw-test"
    assert path.read_bytes() == before
