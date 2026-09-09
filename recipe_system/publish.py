"""Offline publication with explicit redistribution and presentation boundaries."""

from __future__ import annotations

import html
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

from .catalog import build_catalog, categories, source_url
from .core import atomic_json, load_yaml, read_jsonl

FORBIDDEN = re.compile(r"\b(?:tsp|tbsp|teaspoons?|tablespoons?)\b", re.IGNORECASE)


def clean(value, key=None):
    """Metric rendering never exposes original ingredient prose or unconverted units."""
    from .normalize import metric_text

    if isinstance(value, str):
        if key in {
            "source_url",
            "original_source_url",
            "source_license_url",
            "source",
            "image_url",
            "url",
            "image_source_url",
            "source_path",
            "source_recipe_id",
        }:
            return value
        value = metric_text(value)
        return FORBIDDEN.sub("[volume measure unavailable]", value)
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {key: clean(item, key) for key, item in value.items()}
    return value


def _json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def publish(root):
    root = Path(root)
    matches = {row["recipe_id"]: row for row in read_jsonl(root / "data/matches/results.jsonl")}
    personal = _json(root / "data/personal/recipes.json", {})
    records = []
    normalized = read_jsonl(root / "data/recipes/normalized/recipes.jsonl")
    groups = read_jsonl(root / "data/recipes/duplicates/groups.jsonl")
    representatives = {rid: g["representative_id"] for g in groups for rid in g["recipe_ids"]}
    aliases = (
        load_yaml(root / "config/ingredient-aliases.yaml")
        if (root / "config/ingredient-aliases.yaml").exists()
        else {}
    )
    withheld, excluded, duplicate_aliases = [], [], {}

    fields = (
        "id",
        "title",
        "cuisine",
        "servings",
        "active_minutes",
        "total_minutes",
        "equipment",
        "cooking_method",
        "major_protein",
        "vegetables",
        "tags",
        "nutrition",
        "source",
        "source_url",
        "original_source_url",
        "source_license_url",
        "source_license",
        "attribution",
        "raw_id",
        "source_revision",
        "source_path",
        "retrieved_at",
        "normalization_warnings",
        "quality_issues",
    )
    for raw in normalized:
        identifier = raw.get("id", raw.get("recipe_id"))
        if not identifier:
            excluded.append(
                {"raw_id": raw.get("raw_id"), "reason": "missing stable recipe identifier"}
            )
            continue
        if representatives.get(identifier, identifier) != identifier:
            duplicate_aliases[identifier] = representatives[identifier]
            continue
        recipe = {key: raw.get(key) for key in fields}
        recipe["id"] = raw.get("id", raw.get("recipe_id"))
        recipe["ingredients"] = [
            {
                key: item.get(key)
                for key in (
                    "canonical_ingredient",
                    "quantity",
                    "quantity_max",
                    "unit",
                    "optional",
                    "display",
                    "package",
                    "count_unit",
                )
            }
            for item in raw.get("ingredients", [])
        ]
        recipe["instructions"] = (
            raw.get("instructions", []) if raw.get("publication_allowed") is True else []
        )
        recipe["publication_allowed"] = raw.get("publication_allowed") is True
        recipe["match"] = matches.get(
            recipe["id"], {"status": "unknown", "reasons": ["Recipe has not been evaluated."]}
        )
        recipe["cooking_method"] = recipe["match"].get("cooking_method", recipe["cooking_method"])
        recipe["categories"] = categories(recipe, aliases)
        recipe["url"] = source_url(recipe)
        if not recipe["publication_allowed"]:
            withheld.append(
                {
                    "recipe_id": recipe["id"],
                    "source_url": recipe.get("source_url"),
                    "reason": "instruction redistribution permission is not established; ingredients and source link remain published",
                }
            )
        recipe["personal"] = personal.get(recipe["id"], {})
        records.append(clean(recipe))
    records.sort(
        key=lambda row: (
            -(row["match"].get("total_score") or 0),
            (row.get("title") or "").casefold(),
            row["id"],
        )
    )
    atomic_json(
        root / "site/content/publication-report.json",
        {
            "normalized_records": len(normalized),
            "unique_recipes": len(records) + len(excluded),
            "published_recipes": len(records),
            "excluded_recipes": excluded,
            "instructions_withheld": withheld,
            "duplicate_aliases": duplicate_aliases,
        },
    )
    data = {"recipes": records}
    atomic_json(root / "site/content/recipes.json", data)
    return data


def esc(value):
    return html.escape(str(value if value is not None else "Unknown"), quote=True)


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def visible_text(document):
    parser = _VisibleText()
    parser.feed(document)
    return " ".join(parser.parts)


def _page(title, body, prefix=""):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{esc(title)} · My Recipes</title><link rel="stylesheet" href="{prefix}style.css"><script defer src="{prefix}hidden.js"></script></head><body><main>{body}</main></body></html>'''


def build(root):
    root = Path(root)
    data = _json(root / "site/content/recipes.json", {"recipes": []})
    dist = root / "site/dist"
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    for name in ("style.css", "hidden.js", "catalog.js"):
        source = root / "site" / name
        if not source.exists():
            source = Path(__file__).resolve().parents[1] / "site" / name
        shutil.copyfile(source, dist / name)
    manifest = build_catalog(root, data["recipes"], dist)
    return {
        "pages": 1,
        "recipe_detail_pages": 0,
        "catalog": manifest["categories"],
        "missing_source_urls": len(manifest["missing_source_urls"]),
        "output": str(dist),
    }
