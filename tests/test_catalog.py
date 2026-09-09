import json
import shutil
from pathlib import Path

from recipe_system.catalog import categories, recipe_card, source_url
from recipe_system.core import write_jsonl
from recipe_system.publish import build, publish

ROOT = Path(__file__).resolve().parents[1]


def setup_catalog(tmp_path, count=125):
    (tmp_path / "site").mkdir()
    for name in ["hidden.js", "catalog.js", "style.css"]:
        shutil.copyfile(ROOT / "site" / name, tmp_path / "site" / name)
    recipes = []
    matches = []
    for n in range(count):
        recipes.append(
            {
                "id": f"row-{n:03}",
                "raw_id": f"raw-{n}",
                "title": "Same title" if n < 2 else f"Recipe {n:03}",
                "cuisine": "Italian" if n % 2 else None,
                "ingredients": [{"canonical_ingredient": "tomato", "quantity": 100, "unit": "g"}],
                "instructions": ["Cook tomatoes."],
                "publication_allowed": True,
                "source_url": "https://example.test/recipe",
                "total_minutes": 20 if n % 2 else None,
                "cooking_method": ["oven"],
                "major_protein": "chicken breast",
            }
        )
        matches.append(
            {
                "recipe_id": f"row-{n:03}",
                "total_score": 50,
                "foodlion_coverage": 0.8,
                "meal_type": "Dessert" if n == 1 else "Main dish",
                "ranking_representative": True,
                "discovery_representative": n != 1,
                "everyday_eligible": n != 1,
            }
        )
    write_jsonl(tmp_path / "data/recipes/normalized/recipes.jsonl", recipes)
    write_jsonl(tmp_path / "data/matches/results.jsonl", matches)
    return recipes


def test_display_title_suffix_is_conservative():
    from recipe_system.catalog import display_title

    for original, expected in {
        "西红柿炒鸡蛋做法": "西红柿炒鸡蛋",
        "红烧肉做法": "红烧肉",
        "凉拌豆腐做法": "凉拌豆腐",
        "菠菜炒鸡蛋的做法": "菠菜炒鸡蛋",
        "糖醋排骨的做法 ": "糖醋排骨",
        "做法": "做法",
        "做法不同的红烧肉": "做法不同的红烧肉",
        "红烧肉做法比较": "红烧肉做法比较",
        "红烧肉的不同做法": "红烧肉的不同做法",
        "两种做法": "两种做法",
        "传统做法": "传统做法",
        "Pasta": "Pasta",
    }.items():
        assert display_title(original) == expected
        assert display_title(expected) == expected


def test_complete_external_index_and_single_html(tmp_path):
    recipes = setup_catalog(tmp_path)
    before = (tmp_path / "data/recipes/normalized/recipes.jsonl").read_bytes()
    data = publish(tmp_path)
    result = build(tmp_path)
    dist = tmp_path / "site/dist"
    assert result["pages"] == 1 and result["recipe_detail_pages"] == 0
    assert [p.name for p in dist.rglob("*.html")] == ["index.html"]
    index = json.loads((dist / "search-index.json").read_text())
    assert {r["id"] for r in index} == {r["id"] for r in recipes}
    assert len(data["recipes"]) == 125
    assert all(r["url"] == "https://example.test/recipe" for r in index)
    html = (dist / "index.html").read_text()
    assert html.count('target="_blank" rel="noopener noreferrer"') == 125
    assert html.count("data-recipe-id=") == 125
    for marker in [
        "/recipes/",
        'value="score"',
        'data-catalog-filter="coverage"',
        "<img",
        "<h2>Ingredients",
        "<h2>Instructions",
        "app.js",
    ]:
        assert marker not in html
    assert before == (tmp_path / "data/recipes/normalized/recipes.jsonl").read_bytes()
    first = (dist / "search-index.json").read_bytes()
    build(tmp_path)
    assert first == (dist / "search-index.json").read_bytes()
    from recipe_system.catalog_validation import validate_catalog

    assert validate_catalog(tmp_path)["all_recipes_reachable"]


def test_safe_source_preference_and_missing_links(tmp_path):
    assert (
        source_url(
            {"original_source_url": "https://original.test/r", "source_url": "https://repo.test/r"}
        )
        == "https://original.test/r"
    )
    for unsafe in [
        None,
        "",
        "/recipes/local.html",
        "javascript:alert(1)",
        "https:bad",
        "https://",
        "https://user:pass@site.test/",
        "https://site.test/\nfoo",
        "https://site.test:bad/r",
        "https://[bad/r",
    ]:
        assert source_url({"original_source_url": unsafe}) is None
        assert (
            source_url({"original_source_url": unsafe, "source_url": "https://repo.test/r"})
            == "https://repo.test/r"
        )
    records = setup_catalog(tmp_path, 2)
    records[0]["original_source_url"] = "https://original.test/红烧肉"
    records[0]["title"] = "红烧肉的做法"
    records[1]["source_url"] = "javascript:alert(1)"
    write_jsonl(tmp_path / "data/recipes/normalized/recipes.jsonl", records)
    publish(tmp_path)
    result = build(tmp_path)
    assert result["missing_source_urls"] == 1
    index = json.loads((tmp_path / "site/dist/search-index.json").read_text())
    a = next(r for r in index if r["id"] == "row-000")
    assert a["title"] == "红烧肉" and a["url"] == records[0]["original_source_url"]
    b = next(r for r in index if r["id"] == "row-001")
    assert b["url"] is None
    assert "<a " not in recipe_card(b)
    assert "javascript:" not in recipe_card(b)


def test_images_never_enter_index_or_homepage(tmp_path):
    records = setup_catalog(tmp_path, 1)
    records[0]["image"] = {
        "url": "https://example.test/photo.jpg",
        "source_url": "https://example.test/photo",
        "license": "CC-BY-4.0",
    }
    write_jsonl(tmp_path / "data/recipes/normalized/recipes.jsonl", records)
    publish(tmp_path)
    build(tmp_path)
    index = json.loads((tmp_path / "site/dist/search-index.json").read_text())
    assert "image" not in index[0]
    assert "<img" not in (tmp_path / "site/dist/index.html").read_text()


def test_duplicates_and_category_metadata_remain_internal(tmp_path):
    setup_catalog(tmp_path, 3)
    write_jsonl(
        tmp_path / "data/recipes/duplicates/groups.jsonl",
        [{"representative_id": "row-000", "recipe_ids": ["row-000", "row-002"]}],
    )
    data = publish(tmp_path)
    build(tmp_path)
    assert len(data["recipes"]) == 2
    manifest = json.loads((tmp_path / "site/content/catalog-manifest.json").read_text())
    assert manifest["membership"]["meal-type"]["Dessert"] == ["row-001"]
    assert not (tmp_path / "site/dist/recipes").exists()
    assert categories({"title": "Instant Pot dinner", "ingredients": [], "total_minutes": 45})[
        "method"
    ] == ["Pressure cooker"]
