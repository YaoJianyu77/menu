"""Offline completeness, navigation and rendering checks for the published catalog."""

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .catalog import AXES, recipe_url
from .core import read_jsonl
from .publish import FORBIDDEN, visible_text


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.cards = []
        self.images = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article" and "data-recipe-id" in attrs:
            self.current = attrs["data-recipe-id"]
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
            if self.current:
                self.cards.append((self.current, attrs["href"]))
                self.current = None
        if tag == "img":
            self.images.append(attrs.get("src"))

    def handle_endtag(self, tag):
        if tag == "article":
            self.current = None


def validate_catalog(root):
    root = Path(root)
    dist = (root / "site/dist").resolve()
    manifest = json.loads((root / "site/content/catalog-manifest.json").read_text())
    publication = json.loads((root / "site/content/publication-report.json").read_text())
    index = json.loads((dist / "search-index.json").read_text())
    groups = read_jsonl(root / "data/recipes/duplicates/groups.jsonl")
    aliases = {rid: g["representative_id"] for g in groups for rid in g["recipe_ids"]}
    normalized = read_jsonl(root / "data/recipes/normalized/recipes.jsonl")
    expected = {r["id"] for r in normalized if aliases.get(r["id"], r["id"]) == r["id"]}
    excluded = {r.get("recipe_id") for r in publication["excluded_recipes"]}
    assert {r["id"] for r in index} == expected - excluded
    assert len(index) == len({r["id"] for r in index})
    published = json.loads((root / "site/content/recipes.json").read_text())["recipes"]
    ordered = sorted(
        published,
        key=lambda r: (
            -(r.get("match", {}).get("total_score") or 0),
            (r.get("title") or "").casefold(),
            r["id"],
        ),
    )
    assert [r["id"] for r in index] == [r["id"] for r in ordered]
    assert all("score" not in r and "rank" not in r for r in index)
    assert all("ingredients" in r and "methods" in r and "proteins" in r for r in index)
    urls = {r["id"]: r["url"] for r in index}
    pages = {}
    for path in sorted(dist.rglob("*.html")):
        document = path.read_text()
        parser = PageLinks()
        parser.feed(document)
        pages[path] = parser
        assert not FORBIDDEN.search(visible_text(document)), str(path)
        for marker in (
            "/100</dd>",
            "Recommendation score",
            "Why this recipe ranks",
            'data-catalog-filter="min-score"',
            'data-catalog-filter="max-score"',
            'value="score"',
        ):
            assert marker not in document, (path, marker)
        for href in parser.links:
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            destination = (path.parent / unquote(parsed.path)).resolve()
            assert destination.is_relative_to(dist), f"Escaping site link: {href}"
            if destination.is_dir():
                destination = destination / "index.html"
            assert destination.exists(), f"Broken link: {path} -> {href}"
        for identifier, href in parser.cards:
            assert identifier in urls
            assert (path.parent / urlsplit(href).path).resolve() == dist / urls[identifier]
    for row in index:
        path = dist / row["url"]
        text = path.read_text()
        assert row["url"] == recipe_url(row["id"])
        assert 'id="recipe-data"' in text
        assert (
            text.index("<h2>Ingredients")
            < text.index("<h2>Instructions")
            < text.index("<h2>Food Lion ingredients")
            < text.index("My kitchen notes")
            < text.index("Attribution:")
        )
        assert bool(pages[path].images) == bool(row["image"])
        if row["image"]:
            assert pages[path].images == [row["image"]["url"]]

    def listing_ids(directory):
        files = [directory / "index.html"] + sorted(
            directory.glob("page-*.html"), key=lambda p: int(p.stem.split("-")[-1])
        )
        return [rid for path in files for rid, _ in pages[path].cards]

    all_ids = listing_ids(dist)
    assert all_ids == [r["id"] for r in index]
    for axis in AXES:
        for label, ids in manifest["membership"][axis].items():
            field = {
                "cuisine": "cuisines",
                "meal-type": "meal_type",
                "protein": "proteins",
                "method": "methods",
                "time": "time_categories",
            }[axis]
            assert [
                r["id"]
                for r in index
                if (label in r[field] if isinstance(r[field], list) else label == r[field])
            ] == ids
        assert not (dist / axis).exists()
    assert not (dist / "recommended").exists()
    assert not (dist / "recipes/index.html").exists()
    return {
        "unique_normalized_recipes": len(expected),
        "recipes_published": len(index),
        "recipe_detail_pages": len(index),
        "recipes_with_images": sum(bool(r["image"]) for r in index),
        "categories": manifest["categories"],
        "all_recipes_reachable": True,
        "recipe_card_links": "passed",
        "category_membership": "passed",
        "search_index_completeness": "passed",
        "deterministic_order": "passed",
        "metric_rendering": "passed",
        "all_local_links": "passed",
        "static_pages": len(pages),
        "excluded_recipes": publication["excluded_recipes"],
        "instructions_linked_to_source": len(publication["instructions_withheld"]),
    }


if __name__ == "__main__":
    print(json.dumps(validate_catalog("."), indent=2))
