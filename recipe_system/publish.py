"""Offline publication with explicit redistribution and presentation boundaries."""

from __future__ import annotations

import html
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from .core import atomic_json, read_jsonl

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
    for raw in read_jsonl(root / "data/recipes/normalized/recipes.jsonl"):
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
        recipe["personal"] = personal.get(recipe["id"], {})
        records.append(clean(recipe))
    records.sort(
        key=lambda row: (
            not row["match"].get(
                "discovery_representative", row["match"].get("ranking_representative", True)
            ),
            -(row["match"].get("total_score") or 0),
            row["id"],
        )
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
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{esc(title)} · Everyday recipes</title><link rel="stylesheet" href="{prefix}style.css"><script defer src="{prefix}app.js"></script></head><body><header><a href="{prefix}index.html">Everyday recipes</a><span>Williamsburg, Virginia · Personal collection</span></header><main>{body}</main><footer>Food Lion compatibility reflects ingredients the store generally sells. Local stock may vary.</footer></body></html>'''


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
    for name in ("style.css", "app.js"):
        shutil.copyfile(root / "site" / name, dist / name)
    cards = []
    everyday_count = 0
    for row in data["recipes"]:
        identifier = row["id"]
        filename = re.sub(r"[^a-zA-Z0-9_-]", "_", identifier)
        # IDs are also retained in page data, so filename sanitization cannot alter identity.
        match = row["match"]
        coverage = match.get("foodlion_coverage")
        coverage_text = f"{coverage:.0%}" if coverage is not None else "Unknown"
        status = match.get("score_band", "Not ranked")
        meal_type = match.get("meal_type", "Main dish")
        effort = match.get("effort_level", "Unknown")
        total_text = (
            f"{row['total_minutes']} min"
            if row.get("total_minutes") is not None
            else "Time not listed"
        )
        active_text = (
            f"{row['active_minutes']} min"
            if row.get("active_minutes") is not None
            else "Not listed"
        )
        attrs = {
            "name": row.get("title") or "Untitled recipe",
            "cuisine": row.get("cuisine") or "Unknown",
            "status": status,
            "representative": str(
                match.get("discovery_representative", match.get("ranking_representative", True))
            ).lower(),
            "total": row.get("total_minutes"),
            "active": row.get("active_minutes"),
            "protein": row.get("major_protein") or "Unknown",
            "method": "|".join(row.get("cooking_method") or []),
            "coverage": coverage,
            "everyday": str(match.get("everyday_eligible", True)).lower(),
            "effort": effort,
            "meal": meal_type,
            "unknown": match.get("unknown_ingredient_count"),
        }
        attr_html = " ".join(
            f'data-{key}="{esc(value) if value is not None else ""}"'
            for key, value in attrs.items()
        )
        initially_visible = match.get("everyday_eligible", True) and match.get(
            "discovery_representative", match.get("ranking_representative", True)
        )
        everyday_count += int(initially_visible)
        initial_hidden = "" if initially_visible else " hidden"
        cards.append(
            f'<article class="card" {attr_html}{initial_hidden}><span class="badge">{esc(meal_type)}</span><h2><a href="recipes/{filename}.html">{esc(row.get("title"))}</a></h2><p>{esc(row.get("cuisine") or "Cuisine not listed")} · {esc(total_text)}</p><dl><div><dt>Score</dt><dd>{esc(match.get("total_score"))}/100</dd></div><div><dt>Effort</dt><dd>{esc(effort)}</dd></div><div><dt>Food Lion compatibility</dt><dd>{coverage_text}</dd></div></dl></article>'
        )
        ingredient_rows = []
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
                f"<li><span>{ingredient_label}{' (optional)' if item.get('optional') else ''}</span><small data-availability='{esc(availability)}'>Food Lion: {esc(availability_label)}</small>{details}</li>"
            )
        instructions = (
            '<ol class="steps">'
            + "".join(f"<li>{esc(step)}</li>" for step in row["instructions"])
            + "</ol>"
            if row["instructions"]
            else "<p>Open the original recipe for the cooking instructions. Cooking instructions are available at the source link below.</p>"
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
        body = f'''<a class="back" href="../index.html">← Browse recipes</a><section class="recipe-head"><span class="badge">{esc(meal_type)} · {esc(status)}</span><h1>{esc(row.get("title"))}</h1><p>{esc(row.get("cuisine"))} · {esc(row.get("servings"))} servings</p><dl><div><dt>Recommendation</dt><dd>{esc(match.get("total_score"))}/100</dd></div><div><dt>Active time</dt><dd>{esc(active_text)}</dd></div><div><dt>Total time</dt><dd>{esc(total_text)}</dd></div><div><dt>Food Lion compatibility</dt><dd>{coverage_text}</dd></div><div><dt>Effort</dt><dd>{esc(effort)}</dd></div></dl><p>Local stock may vary.</p><p>Method: {esc(", ".join(row.get("cooking_method") or []) or "Unknown")} · Protein: {esc(row.get("major_protein"))}</p></section>{quality_warning}<div class="recipe-columns"><section><h2>Ingredients</h2><ul class="ingredients">{"".join(ingredient_rows)}</ul></section><section><h2>Instructions</h2>{instructions}<a class="button" href="{esc(_url(row.get("original_source_url") or row.get("source_url")))}" rel="noreferrer">Open original recipe ↗</a></section></div><details><summary>Why this recipe ranks here</summary><p>Food Lion compatibility: {esc(match.get("foodlion_score"))}/35 · Convenience: {esc(match.get("time_score"))}/25 · Meal balance: {esc(match.get("nutrition_score"))}/25 · Simplicity: {esc(match.get("simplicity_score"))}/15</p><p>Meal balance reflects the ingredients, not a calculated nutrition label.</p><ul>{"".join(f"<li>{esc(reason)}</li>" for reason in match.get("reasons", []))}</ul></details><details><summary>Nutrition & source</summary><p>Nutrition: {esc(json.dumps(row.get("nutrition"), ensure_ascii=False) if row.get("nutrition") else "Not provided")}</p><p>Attribution: {esc(row.get("attribution") or row.get("source"))}<br>License: {esc(row.get("source_license"))}<br>{license_link}<br><a href="{esc(_url(row.get("source_url")))}" rel="noreferrer">Recipe source ↗</a></p></details><section class="personal"><h2>My kitchen notes</h2><p>Saved in this browser. Export a backup to preserve your annotations.</p><form id="personal-form"><label><input type="checkbox" name="favorite"> Favorite</label><label><input type="checkbox" name="cooked"> Cooked</label><label><input type="checkbox" name="would_cook_again"> Would cook again</label><label>Rating<select name="rating"><option value="">Unrated</option>{"".join(f"<option>{n}</option>" for n in range(1, 6))}</select></label><label>Last cooked<input type="date" name="last_cooked_date"></label><label class="wide">Notes<textarea name="notes" rows="4"></textarea></label><label class="wide">Modifications<textarea name="modifications" rows="2"></textarea></label><button type="submit">Save notes</button><output id="save-status" aria-live="polite"></output></form><button id="export-notes" type="button">Export all notes</button><label class="import-label">Import notes<input id="import-notes" type="file" accept="application/json"></label></section><script id="recipe-data" type="application/json">{payload}</script>'''
        output = _page(row.get("title"), body, "../")
        if FORBIDDEN.search(visible_text(output)):
            raise ValueError(f"Forbidden output unit in {identifier}")
        (dist / "recipes" / f"{filename}.html").write_text(output)
    presets = (
        ("everyday", "Best everyday meals"),
        ("quick", "Under 30 minutes"),
        ("easy", "Easy / low-effort"),
        ("airfryer", "Air fryer"),
        ("onepan", "One-pan / one-pot"),
        ("compatible", "High Food Lion compatibility"),
        ("cuisine", "By cuisine"),
        ("all", "All recipes"),
    )
    preset_html = "".join(
        f'<button type="button" data-preset="{key}" aria-pressed="{str(key == "everyday").lower()}">{label}</button>'
        for key, label in presets
    )
    body = f"""<h1>What’s for dinner?</h1><p class="intro">Practical meals, ordinary ingredients, and less time in the kitchen. Local stock may vary.</p><nav class="presets" aria-label="Find a meal">{preset_html}</nav><section class="filters" aria-label="Recipe filters"><label class="search">Search recipes<input id="search" type="search" placeholder="Recipe name…"></label>{_options("Cuisine", "cuisine")}{_options("Recommendation", "status")}{_options("Meal type", "meal")}{_options("Main protein", "protein")}{_options("Cooking method", "method")}<label>Max total minutes<input data-filter="total" type="number" min="0" placeholder="Any"></label><label>Max active minutes<input data-filter="active" type="number" min="0" placeholder="Any"></label><label>Min Food Lion compatibility %<input data-filter="coverage" type="number" min="0" max="100" placeholder="Any"></label><label><input id="include-variants" type="checkbox"> Include similar versions</label><button id="reset" type="button">Reset filters</button></section><p id="count" role="status">{everyday_count} recipes</p><section id="cards" class="cards">{"".join(cards)}</section><p id="empty" {"hidden" if cards else ""}>No recipes match. Try another category or clear a filter.</p>"""
    (dist / "index.html").write_text(_page("Browse", body))
    return {"pages": len(cards) + 1, "output": str(dist)}
