"""Ingredient search shares persisted canonical vocabulary and original ingredient evidence."""

import subprocess
from pathlib import Path

from recipe_system.core import atomic_json, write_jsonl
from recipe_system.publish import publish
from tests.test_catalog import setup_catalog


def test_search_engine():
    subprocess.run(
        ["node", "tests/browser/search.cjs"],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
    )


def test_search_publication_preserves_aliases_and_raw_title(tmp_path):
    recipes = setup_catalog(tmp_path, 1)
    recipes[0]["ingredients"][0]["original_text"] = "100 g fresh tomatoes, chopped"
    write_jsonl(tmp_path / "data/recipes/normalized/recipes.jsonl", recipes)
    write_jsonl(
        tmp_path / "data/recipes/raw/test.jsonl",
        [{"id": "raw-0", "title": "Original tomato dinner"}],
    )
    # JSON is valid YAML; this exercises the same existing alias schema.
    atomic_json(
        tmp_path / "config/ingredient-aliases.yaml",
        {"ingredients": {"tomato": {"aliases": ["tomatoes", "roma tomatoes"]}}},
    )
    result = publish(tmp_path)["recipes"][0]
    assert result["search_original_title"] == "Original tomato dinner"
    terms = result["ingredient_search"][0]["terms"]
    assert "100 g fresh tomatoes, chopped" in terms
    assert "roma tomatoes" in terms
