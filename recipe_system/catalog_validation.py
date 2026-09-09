"""Validate the complete single-page source index against persisted inputs."""

import json
from html.parser import HTMLParser
from pathlib import Path

from .catalog import display_title, source_url
from .core import read_jsonl
from .publish import FORBIDDEN, visible_text


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
    assert [p.relative_to(dist).as_posix() for p in dist.rglob("*.html")] == ["index.html"]
    document = (dist / "index.html").read_text()
    page = PageLinks()
    page.feed(document)
    assert page.ids == [r["id"] for r in index]
    assert not page.images
    assert not FORBIDDEN.search(visible_text(document))
    for row, original in zip(index, ordered):
        assert row["title"] == display_title(original.get("title"))
        assert row["url"] == source_url(original)
        assert "score" not in row and "image" not in row and "instructions" not in row
    urls = {r["id"]: r["url"] for r in index}
    assert len(page.links) == sum(bool(r["url"]) for r in index)
    for rid, attrs in page.links:
        assert attrs["href"] == urls[rid]
        assert attrs["target"] == "_blank"
        assert set(attrs["rel"].split()) >= {"noopener", "noreferrer"}
    for marker in [
        'value="score"',
        'data-catalog-filter="coverage"',
        "app.js",
        "recipe-data",
        'href="recipes/',
    ]:
        assert marker not in document
    return {
        "recipes_published": len(index),
        "recipe_detail_pages": 0,
        "static_pages": 1,
        "all_recipes_reachable": True,
        "external_links": "passed",
        "missing_source_urls": sum(not r["url"] for r in index),
        "deterministic_order": "passed",
        "metric_rendering": "passed",
    }


if __name__ == "__main__":
    print(json.dumps(validate_catalog("."), indent=2))
