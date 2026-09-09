import json
import shutil
from pathlib import Path

from recipe_system.catalog import categories, recipe_card, recipe_url
from recipe_system.core import write_jsonl
from recipe_system.publish import build, publish

ROOT = Path(__file__).resolve().parents[1]


def setup_catalog(tmp_path, count=125):
    (tmp_path / "site").mkdir()
    for name in ["app.js", "catalog.js", "style.css"]:
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


def test_full_unique_catalog_links_pagination_and_search(tmp_path):
    recipes = setup_catalog(tmp_path)
    data = publish(tmp_path)
    result = build(tmp_path)
    assert result["recipe_detail_pages"] == 125
    index = json.loads((tmp_path / "site/dist/search-index.json").read_text())
    assert {r["id"] for r in index} == {r["id"] for r in recipes}
    assert len(index) == len(data["recipes"])
    assert all(r["ingredients"] == ["tomato"] for r in index)
    # Same-title and low-score dessert remain in the full catalog.
    assert sum(r["title"] == "Same title" for r in index) == 2
    pages = [(tmp_path / "site/dist" / p).read_text() for p in ["index.html", "page-2.html"]]
    for row in index:
        assert any(f'href="{row["url"]}"' in page for page in pages)
        assert (tmp_path / "site/dist" / row["url"]).exists()
    assert sum(page.count("data-recipe-id=") for page in pages) == 125
    first = (tmp_path / "site/dist/search-index.json").read_bytes()
    build(tmp_path)
    assert first == (tmp_path / "site/dist/search-index.json").read_bytes()


def test_categories_are_all_score_levels_and_no_invented_cuisine(tmp_path):
    setup_catalog(tmp_path, 3)
    publish(tmp_path)
    build(tmp_path)
    manifest = json.loads((tmp_path / "site/content/catalog-manifest.json").read_text())
    assert manifest["membership"]["cuisine"]["Unknown"] == ["row-002", "row-000"]
    assert manifest["membership"]["meal-type"]["Dessert"] == ["row-001"]
    assert set(manifest["membership"]["protein"]["Chicken"]) == {"row-000", "row-001", "row-002"}
    assert set(manifest["membership"]["method"]["Oven"]) == {"row-000", "row-001", "row-002"}
    assert manifest["membership"]["time"]["Under 30 min"] == ["row-001"]
    for path in [
        "cuisine/unknown",
        "meal-type/dessert",
        "protein/chicken",
        "method/oven",
        "time/under-30-min",
    ]:
        assert not (tmp_path / "site/dist" / path / "index.html").exists()


def test_recipe_urls_stable_and_collision_safe():
    assert recipe_url("abc") == "recipes/abc.html"
    assert recipe_url("a/b") != recipe_url("a_b")
    assert recipe_url("a/b") == recipe_url("a/b")


def test_images_and_no_image_cards(tmp_path):
    records = setup_catalog(tmp_path, 2)
    records[0]["image"] = {
        "url": "https://example.test/photo.jpg",
        "source_url": "https://example.test/photo",
        "license": "CC-BY-4.0",
        "attribution": "Photographer",
    }
    write_jsonl(tmp_path / "data/recipes/normalized/recipes.jsonl", records)
    publish(tmp_path)
    build(tmp_path)
    index = json.loads((tmp_path / "site/dist/search-index.json").read_text())
    image = next(r for r in index if r["id"] == "row-000")
    none = next(r for r in index if r["id"] == "row-001")
    assert "<img" not in recipe_card(image)
    assert "<figure" not in recipe_card(image)
    assert "<img" not in recipe_card(none)
    page = (tmp_path / "site/dist" / image["url"]).read_text()
    assert "Photographer" in page and "CC-BY-4.0" in page
    assert (
        page.index("<h1>")
        < page.index("<figure>")
        < page.index("<h2>Ingredients")
        < page.index("<h2>Instructions")
        < page.index("<h2>Food Lion ingredients")
        < page.index("My kitchen notes")
        < page.index("Attribution:")
    )


def test_exact_duplicates_redirect_but_similar_titles_remain(tmp_path):
    setup_catalog(tmp_path, 3)
    write_jsonl(
        tmp_path / "data/recipes/duplicates/groups.jsonl",
        [{"representative_id": "row-000", "recipe_ids": ["row-000", "row-002"]}],
    )
    data = publish(tmp_path)
    build(tmp_path)
    assert len(data["recipes"]) == 2
    assert "row-000.html" in (tmp_path / "site/dist/recipes/row-002.html").read_text()
    report = json.loads((tmp_path / "site/content/publication-report.json").read_text())
    assert report["excluded_recipes"] == []
    assert report["duplicate_aliases"] == {"row-002": "row-000"}


def test_time_boundaries_and_explicit_method_evidence():
    row = {"title": "Instant Pot dinner", "match": {}, "ingredients": [], "total_minutes": 45}
    c = categories(row)
    assert c["time"] == ["30–45 min"]
    assert c["method"] == ["Pressure cooker"]
    assert c["cuisine"] == ["Unknown"]
    assert c["protein"] == ["Other"]


def test_complete_offline_catalog_validation(tmp_path):
    from recipe_system.catalog_validation import validate_catalog

    setup_catalog(tmp_path, 125)
    publish(tmp_path)
    build(tmp_path)
    report = validate_catalog(tmp_path)
    assert report["recipes_published"] == 125
    assert report["all_recipes_reachable"]
    assert report["all_local_links"] == "passed"


def test_single_home_catalog_has_no_dashboard_or_scores(tmp_path):
    setup_catalog(tmp_path, 125)
    publish(tmp_path)
    build(tmp_path)
    dist = tmp_path / "site/dist"
    index = json.loads((dist / "search-index.json").read_text())
    assert all(
        "score" not in row and "rank" not in row and "recommended" not in row for row in index
    )
    home = (dist / "index.html").read_text()
    assert "<h1>My Recipes</h1>" in home
    assert home.count("data-catalog-filter=") == 5
    assert 'href="page-2.html"' in home
    assert 'href="index.html"' in (dist / "page-2.html").read_text()
    assert not (dist / "recipes/index.html").exists()
    for directory in ["cuisine", "meal-type", "protein", "method", "time", "recommended"]:
        assert not (dist / directory).exists()
    for path in dist.rglob("*.html"):
        html = path.read_text()
        for marker in [
            "/100",
            "Recommendation",
            "Why this recipe ranks",
            "Minimum score",
            "Maximum score",
            'value="score"',
            'class="site-nav"',
        ]:
            assert marker not in html
    detail = (dist / index[0]["url"]).read_text()
    assert 'data-back-to-recipes href="../index.html"' in detail


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


def test_clean_titles_and_metadata_only_affect_rendering(tmp_path):
    records = setup_catalog(tmp_path, 2)
    records[0]["title"] = "红烧肉的做法"
    records[0]["cuisine"] = "Chinese"
    records[0]["total_minutes"] = 23
    records[1]["cooking_method"] = []
    records[1]["total_minutes"] = None
    normalized = tmp_path / "data/recipes/normalized/recipes.jsonl"
    write_jsonl(normalized, records)
    raw = tmp_path / "data/recipes/raw/test.jsonl"
    write_jsonl(raw, [{"id": "raw-0", "title": "红烧肉的做法"}])
    before = {
        path: path.read_bytes()
        for path in [normalized, raw, tmp_path / "data/matches/results.jsonl"]
    }
    published = publish(tmp_path)
    build(tmp_path)
    assert all(path.read_bytes() == content for path, content in before.items())
    assert next(r for r in published["recipes"] if r["id"] == "row-000")["title"] == "红烧肉的做法"
    dist = tmp_path / "site/dist"
    index = json.loads((dist / "search-index.json").read_text())
    row = next(r for r in index if r["id"] == "row-000")
    assert row["title"] == "红烧肉"
    assert row["cuisine"] == "Chinese"
    assert row["coverage"] == 0.8
    assert row["url"] == "recipes/row-000.html"
    card = recipe_card(row)
    assert "红烧肉</a>" in card
    assert "23 min · Oven" in card
    for text in ["Chinese", "Main dish", "80%", "Food Lion"]:
        assert text not in card
    detail = (dist / row["url"]).read_text()
    assert "<title>红烧肉 · My Recipes</title>" in detail
    head = detail.split('<section class="recipe-head">')[1].split("</section>")[0]
    assert "<h1>红烧肉</h1>" in head and "23 min · Oven" in head
    for text in ["Chinese", "Main dish", "%", "Unknown", "Food Lion"]:
        assert text not in head
    none = recipe_card(next(r for r in index if r["id"] == "row-001"))
    assert 'class="row-meta"' not in none
    assert "Unknown" not in none
    assert "%" not in (dist / "index.html").read_text()
