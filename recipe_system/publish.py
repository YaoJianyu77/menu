"""Offline publication with explicit redistribution and presentation boundaries."""

from __future__ import annotations

import html
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from .catalog import build_catalog, categories, category_links, image_html, recipe_url
from .core import atomic_json, load_yaml, read_jsonl
from .recipe_images import select_image

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
    raw_images = {
        r["id"]: {k: v for k, v in r.items() if k == "id" or k.startswith("image")}
        for path in (root / "data/recipes/raw").glob("*.jsonl")
        for r in read_jsonl(path)
    }
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
        recipe["url"] = recipe_url(recipe["id"])
        recipe["image"] = select_image(raw, raw_images.get(raw.get("raw_id")))
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


def _url(value):
    return value if isinstance(value, str) and urlparse(value).scheme in {"http", "https"} else "#"


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
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{esc(title)} · My Recipes</title><link rel="stylesheet" href="{prefix}style.css"><script defer src="{prefix}app.js"></script></head><body><main>{body}</main><footer>Food Lion compatibility reflects ingredients the store generally sells. Local stock may vary.</footer></body></html>'''


def _options(label, key):
    return (
        f'<label>{label}<select data-filter="{key}"><option value="">All</option></select></label>'
    )


def build(root):
    root = Path(root)
    data = _json(root / "site/content/recipes.json", {"recipes": [], "collections": []})
    dist = root / "site/dist"
    # Remove only generated output, never source content.
    if dist.exists():
        shutil.rmtree(dist)
    (dist / "recipes").mkdir(parents=True)
    for name in ("style.css", "app.js", "catalog.js"):
        source = root / "site" / name
        if not source.exists():
            source = Path(__file__).resolve().parents[1] / "site" / name
        shutil.copyfile(source, dist / name)
    for row in data["recipes"]:
        identifier = row["id"]
        row.setdefault("categories", categories(row))
        row.setdefault("url", recipe_url(identifier))
        match = row["match"]
        coverage = match.get("foodlion_coverage")
        coverage_text = f"{coverage:.0%}" if coverage is not None else "Unknown"
        total_text = (
            f"{row['total_minutes']:g} min"
            if isinstance(row.get("total_minutes"), (int, float))
            else "Unknown"
        )
        active_text = (
            f"{row['active_minutes']:g} min"
            if isinstance(row.get("active_minutes"), (int, float))
            else None
        )
        ingredient_rows = []
        availability_rows = []
        substitutions = []
        ingredient_matches = match.get("ingredient_matches") or []
        for item in row["ingredients"]:
            name = item.get("canonical_ingredient") or "Unparsed ingredient — see source"
            quantity = " ".join(
                str(item[key]) for key in ("quantity", "unit") if item.get(key) is not None
            )
            if item.get("quantity_max") is not None:
                quantity = f"{item.get('quantity')}–{item['quantity_max']} {item.get('unit') or ''}"
            ingredient_label = (
                esc(item["display"])
                if item.get("display")
                else f"<strong>{esc(quantity)}</strong> {esc(name)}"
            )
            evidence = next(
                (
                    m
                    for m in ingredient_matches
                    if m.get("canonical_ingredient", m.get("ingredient")) == name
                ),
                {},
            )
            availability = evidence.get("status", "unknown")
            compatibility = evidence.get("compatibility_status")
            availability_label = {"yes": "Yes", "probably": "Probably", "unknown": "Unknown"}.get(
                compatibility
            ) or {
                "verified_available": "Yes",
                "available": "Yes",
                "likely_available": "Yes",
                "probably_available": "Probably",
                "unknown": "Unknown",
                "unavailable": "Unknown",
            }.get(availability, "Unknown")
            details = ""
            evidence_urls = [
                item.get("source_url")
                for item in evidence.get("evidence", [])
                if isinstance(item, dict) and _url(item.get("source_url")) != "#"
            ]
            if evidence_urls:
                details = f'<details><summary>Product links</summary><a href="{esc(evidence_urls[0])}" rel="noreferrer">Food Lion product ↗</a></details>'
            ingredient_rows.append(
                f"<li>{ingredient_label}{' (optional)' if item.get('optional') else ''}</li>"
            )
            availability_rows.append(
                f"<li>{esc(name)} — <span>Food Lion: {esc(availability_label)}</span>{details}</li>"
            )
            if evidence.get("substitution"):
                substitutions.append(f"<li>{esc(name)}: {esc(evidence['substitution'])}</li>")
        instructions = (
            '<ol class="steps">'
            + "".join(f"<li>{esc(step)}</li>" for step in row["instructions"])
            + "</ol>"
            if row["instructions"]
            else "<p>Open the original recipe for cooking instructions.</p>"
        )
        payload = json.dumps(
            {"id": identifier, "personal": row.get("personal", {})}, ensure_ascii=False
        ).replace("<", "\\u003c")
        license_link = (
            f'<a href="{esc(_url(row.get("source_license_url")))}" rel="noreferrer">Repository license ↗</a>'
            if _url(row.get("source_license_url")) != "#"
            else "Repository license: unknown"
        )
        quality_issues = match.get("quality", {}).get("quality_issues") or row.get("quality_issues")
        quality_warning = (
            "<aside>Some recipe details need checking. Read the original recipe before cooking.</aside>"
            if quality_issues
            else ""
        )
        active_html = (
            f"<div><dt>Active time</dt><dd>{esc(active_text)}</dd></div>" if active_text else ""
        )
        servings_html = (
            f"<div><dt>Servings</dt><dd>{esc(row['servings'])}</dd></div>"
            if row.get("servings") is not None
            else ""
        )
        source_category_links = category_links(row)
        availability_html = (
            "<section><h2>Food Lion ingredients</h2><p>Local stock may vary. Unknown does not mean not sold.</p><ul>"
            + "".join(availability_rows)
            + "</ul></section>"
        )
        substitution_html = (
            "<section><h2>Substitutions</h2><ul>" + "".join(substitutions) + "</ul></section>"
            if substitutions
            else ""
        )
        body = f'''<a class="back" data-back-to-recipes href="../index.html">← Back to recipes</a><section class="recipe-head"><h1>{esc(row.get("title"))}</h1>{image_html(row.get("image"))}{source_category_links}<dl><div><dt>Food Lion compatibility</dt><dd>{coverage_text}</dd></div><div><dt>Total time</dt><dd>{esc(total_text)}</dd></div>{active_html}{servings_html}</dl><p>Local stock may vary.</p></section>{quality_warning}<div class="recipe-columns"><section><h2>Ingredients</h2><ul class="ingredients">{"".join(ingredient_rows)}</ul></section><section><h2>Instructions</h2>{instructions}<a class="button" href="{esc(_url(row.get("original_source_url") or row.get("source_url")))}" rel="noreferrer">Open original recipe ↗</a></section></div>{availability_html}{substitution_html}<details class="personal"><summary>My kitchen notes</summary><p>Saved in this browser. Export a backup to preserve your annotations.</p><form id="personal-form"><label><input type="checkbox" name="favorite"> Favorite</label><label><input type="checkbox" name="cooked"> Cooked</label><label><input type="checkbox" name="would_cook_again"> Would cook again</label><label>Rating<select name="rating"><option value="">Unrated</option>{"".join(f"<option>{n}</option>" for n in range(1, 6))}</select></label><label>Last cooked<input type="date" name="last_cooked_date"></label><label class="wide">Notes<textarea name="notes" rows="4"></textarea></label><label class="wide">Modifications<textarea name="modifications" rows="2"></textarea></label><button type="submit">Save notes</button><output id="save-status" aria-live="polite"></output></form><button id="export-notes" type="button">Export all notes</button><label class="import-label">Import notes<input id="import-notes" type="file" accept="application/json"></label></details><details><summary>Source attribution</summary><p>Nutrition: {esc(json.dumps(row.get("nutrition"), ensure_ascii=False) if row.get("nutrition") else "Not provided")}</p><p>Attribution: {esc(row.get("attribution") or row.get("source"))}<br>License: {esc(row.get("source_license"))}<br>{license_link}<br><a href="{esc(_url(row.get("source_url")))}" rel="noreferrer">Recipe source ↗</a></p></details><script id="recipe-data" type="application/json">{payload}</script>'''
        output = _page(row.get("title"), body, "../")
        if FORBIDDEN.search(visible_text(output)):
            raise ValueError(f"Forbidden output unit in {identifier}")
        (dist / row["url"]).write_text(output)
    manifest = build_catalog(root, data["recipes"], dist)
    # Old duplicate-record URLs continue to resolve to their final representative.
    report = _json(root / "site/content/publication-report.json", {})
    for old, new in report.get("duplicate_aliases", {}).items():
        target = recipe_url(new).split("/")[-1]
        (dist / recipe_url(old)).write_text(
            f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={target}"><a href="{target}">Open recipe</a>'
        )
    return {
        "pages": len(list(dist.rglob("*.html"))),
        "recipe_detail_pages": len(data["recipes"]),
        "catalog": manifest["categories"],
        "output": str(dist),
    }
