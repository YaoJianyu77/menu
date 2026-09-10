"""Validate the complete catalog, dual links and detail pages against persisted inputs."""

import json
from html.parser import HTMLParser
from pathlib import Path

from .catalog import display_title, recipe_url, source_url
from .core import read_jsonl
from .publish import FORBIDDEN, esc, visible_text


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.current = None
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article":
            self.current = attrs.get("data-recipe-id")
            if self.current:
                self.ids.append(self.current)
        if tag == "a" and self.current:
            self.links.append((self.current, attrs))
        if tag == "img":
            self.images.append(attrs)

    def handle_endtag(self, tag):
        if tag == "article":
            self.current = None


def validate_catalog(root):
    root = Path(root)
    dist = root / "site/dist"
    index = json.loads((dist / "search-index.json").read_text())
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
    groups = read_jsonl(root / "data/recipes/duplicates/groups.jsonl")
    aliases = {rid: g["representative_id"] for g in groups for rid in g["recipe_ids"]}
    expected = {
        r["id"]
        for r in read_jsonl(root / "data/recipes/normalized/recipes.jsonl")
        if aliases.get(r["id"], r["id"]) == r["id"]
    }
    assert {r["id"] for r in index} == expected
    assert len(list(dist.rglob("*.html"))) == len(index) + 1
    assert not any(
        (dist / axis).exists()
        for axis in ["cuisine", "method", "protein", "recommended", "meal-type", "time"]
    )
    document = (dist / "index.html").read_text()
    page = PageLinks()
    page.feed(document)
    assert page.ids == [r["id"] for r in index]
    assert not page.images
    assert not FORBIDDEN.search(visible_text(document))
    for row, original in zip(index, ordered):
        assert row["title"] == display_title(original.get("title"))
        assert row["url"] == recipe_url(row["id"])
        assert row["source_url"] == source_url(original)
        detail = (dist / row["url"]).read_text()
        assert "<h2>Ingredients</h2>" in detail and "<h2>Instructions</h2>" in detail
        assert not FORBIDDEN.search(visible_text(detail))
        assert f"<h1>{esc(row['title'])}</h1>" in detail
        for step in original.get("instructions", []):
            assert esc(step) in detail
        assert "score" not in row and "image" not in row and "instructions" not in row
    urls = {r["id"]: r for r in index}
    assert len(page.links) == len(index) + sum(bool(r["source_url"]) for r in index)
    for rid, attrs in page.links:
        if attrs.get("class") == "source-link":
            assert attrs["href"] == urls[rid]["source_url"]
            assert attrs["target"] == "_blank"
            assert set(attrs["rel"].split()) >= {"noopener", "noreferrer"}
        else:
            assert attrs["href"] == urls[rid]["url"]
            assert "target" not in attrs
    for marker in [
        'value="score"',
        'data-catalog-filter="coverage"',
        "app.js",
        "recipe-data",
    ]:
        assert marker not in document
    return {
        "recipes_published": len(index),
        "recipe_detail_pages": len(index),
        "static_pages": len(index) + 1,
        "all_recipes_reachable": True,
        "external_links": "passed",
        "missing_source_urls": sum(not r["source_url"] for r in index),
        "deterministic_order": "passed",
        "metric_rendering": "passed",
    }


if __name__ == "__main__":
    print(json.dumps(validate_catalog("."), indent=2))
