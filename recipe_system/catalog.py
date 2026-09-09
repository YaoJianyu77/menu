"""Static, complete catalog views over persisted unique recipes; no ranking changes."""

import json
import re
from collections import defaultdict
from urllib.parse import urlsplit

from .core import atomic_json

PAGE_SIZE = 120
AXES = {
    "cuisine": "Cuisine",
    "meal-type": "Meal Type",
    "protein": "Main Protein",
    "method": "Cooking Method",
    "time": "Time",
}
MEALS = [
    "Full meal",
    "Main dish",
    "Breakfast",
    "Sandwich",
    "Pasta",
    "Rice / Grain",
    "Soup / Stew",
    "Salad",
    "Side dish",
    "Snack",
    "Dessert",
    "Baking",
    "Sauce / Condiment",
    "Other",
]
CUISINES = [
    "American",
    "Chinese",
    "Italian",
    "French",
    "Korean",
    "Japanese",
    "Mexican",
    "Mediterranean",
    "Turkish",
    "Indian",
    "Greek",
    "British",
    "Malaysian",
    "Middle Eastern",
    "Asian",
    "Vietnamese",
    "Georgian",
    "Danish",
    "Filipino",
    "Spanish",
    "Portuguese",
    "Moroccan",
    "Indonesian",
    "Lebanese",
    "Cajun",
    "Southern",
    "Tex Mex",
    "Brazilian",
    "Swedish",
    "Norwegian",
    "European",
    "Western",
    "New England",
    "North America",
    "Arabic",
]
CUISINE_ALIASES = {
    "italiana": "Italian",
    "italiensk": "Italian",
    "recettes françaises": "French",
    "mexicaans": "Mexican",
    "aziatisch": "Asian",
    "amerikansk": "American",
    "brasileira": "Brazilian",
    "schweden": "Swedish",
    "европейская": "European",
    "europa": "European",
    "norge": "Norwegian",
    "spanisch und portugiesisch": "Spanish,Portuguese",
}
METHODS = {
    "air fryer": "Air fryer",
    "oven": "Oven",
    "stovetop": "Stovetop",
    "one-pan": "One-pan",
    "one-pot": "One-pot",
    "sheet-pan": "Sheet-pan",
    "pressure cooker": "Pressure cooker",
    "slow cooker": "Slow cooker",
    "microwave": "Microwave",
    "grill": "Grill",
    "no-cook": "No-cook",
}
PROTEIN_GROUPS = {
    "Chicken": {
        "chicken",
        "chicken breast",
        "chicken thigh",
        "chicken wing",
        "chicken leg",
        "chicken drumstick",
        "whole chicken",
    },
    "Beef": {"beef", "ground beef"},
    "Pork": {"pork", "ground pork", "pork belly", "ham", "bacon", "sausage"},
    "Fish": {"salmon", "tuna", "cod", "fish", "tilapia"},
    "Seafood": {"shrimp", "prawn", "crab", "clam", "mussel", "scallop"},
    "Eggs": {"egg"},
    "Tofu": {"tofu"},
    "Beans / Lentils": {"chickpea", "lentil", "black bean", "kidney bean", "bean"},
    "Cheese / Dairy": {
        "cheddar",
        "parmesan",
        "feta",
        "mozzarella",
        "greek yogurt",
        "yogurt",
        "cheese",
    },
}


def source_url(row):
    """Use only persisted, safe HTTP(S) locations; prefer the original recipe."""
    for value in (row.get("original_source_url"), row.get("source_url")):
        if not isinstance(value, str) or not value or re.search(r"[\s<>\\]", value):
            continue
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme in {"http", "https"}
                and parsed.hostname
                and not parsed.username
                and not parsed.password
            ):
                _ = parsed.port  # Reject malformed port values too.
                return value
        except ValueError:
            pass
    return None


def cuisine_labels(value):
    known = {x.casefold(): x for x in CUISINES}
    result = set()
    for token in str(value or "").split(","):
        token = token.strip().casefold()
        translated = CUISINE_ALIASES.get(token, known.get(token, ""))
        result.update(x for x in translated.split(",") if x)
    return sorted(result) or ["Unknown"]


def categories(row, aliases=None):
    match = row.get("match", {})
    meal = match.get("meal_type", "Other")
    meal = {
        "Rice/grain": "Rice / Grain",
        "Soup/stew": "Soup / Stew",
        "Sauce/condiment": "Sauce / Condiment",
    }.get(meal, meal)
    if meal not in MEALS:
        meal = "Other"
    major = row.get("major_protein")
    proteins = [label for label, names in PROTEIN_GROUPS.items() if major in names]
    names = {i.get("canonical_ingredient") for i in row.get("ingredients", [])}
    entries = (aliases or {}).get("ingredients", {})
    if (
        names
        and names <= entries.keys()
        and not any(
            entries[n].get("category") in {"meat", "seafood"}
            or re.search(
                r"chicken|beef|pork|fish|oyster|anchov|gelatin|lard|肉|鱼", n, re.IGNORECASE
            )
            for n in names
        )
    ):
        proteins.append("Vegetarian")
    methods = {METHODS[x] for x in row.get("cooking_method") or [] if x in METHODS}
    text = " ".join([row.get("title") or ""] + (row.get("equipment") or []))
    for method, pattern in [
        ("Pressure cooker", r"pressure cooker|instant pot"),
        ("Slow cooker", r"slow cooker|crock.pot"),
        ("Grill", r"\bgrill(?:ed|ing)?\b"),
    ]:
        if re.search(pattern, text, re.IGNORECASE):
            methods.add(method)
    total = row.get("total_minutes")
    times = []
    if not isinstance(total, (int, float)) or total <= 0:
        times = ["Unknown"]
    else:
        if total < 15:
            times.append("Under 15 min")
        if total < 30:
            times.append("Under 30 min")
        if 30 <= total <= 45:
            times.append("30–45 min")
        if 45 < total <= 60:
            times.append("45–60 min")
        if total > 60:
            times.append("Over 60 min")
    return {
        "cuisine": cuisine_labels(row.get("cuisine")),
        "meal-type": [meal],
        "protein": proteins or ["Other"],
        "method": sorted(methods) or ["Other"],
        "time": times,
    }


def display_title(value):
    """Presentation only: strip a terminal Chinese recipe-label suffix.

    Interior occurrences and phrases describing kinds of methods stay intact.
    Source/published recipe records and identity never change.
    """
    title = value or "Untitled recipe"
    match = re.fullmatch(r"(.+?)(?:的)?做法\s*", title)
    if not match:
        return title
    stem = match[1].rstrip()
    if not re.search(r"[\u3400-\u9fff]", stem):
        return title
    if re.search(
        r"(?:传统|常见|不同|惯用|这种|那种|某种|其他|其它|[一二三四五六七八九十两0-9]+种)$", stem
    ):
        return title
    return stem


def cooking_facts(row):
    facts = []
    if isinstance(row.get("total_minutes"), (int, float)) and row["total_minutes"] > 0:
        facts.append(f"{row['total_minutes']:g} min")
    facts.extend(x for x in row.get("methods", []) if x not in {"Other", "Unknown"})
    return " · ".join(facts)


def index_entry(row):
    cats = row["categories"]
    return {
        "id": row["id"],
        "url": source_url(row),
        "title": display_title(row.get("title")),
        "sort_title": display_title(row.get("title")).casefold(),
        "cuisine": ", ".join(cats["cuisine"]),
        "cuisines": cats["cuisine"],
        "meal_type": cats["meal-type"][0],
        "proteins": cats["protein"],
        "methods": cats["method"],
        "time_categories": cats["time"],
        "total_minutes": row.get("total_minutes"),
        "ingredients": [
            i["canonical_ingredient"]
            for i in row.get("ingredients", [])
            if i.get("canonical_ingredient")
        ],
    }


def recipe_card(row):
    """Compact external-link directory row; no local recipe content."""
    from .publish import esc

    facts = cooking_facts({**row, "methods": row.get("methods", [])[:1]})
    metadata = f'<p class="row-meta">{esc(facts)}</p>' if facts else ""
    title = (
        f'<a title="{esc(row["title"])}" href="{esc(row["url"])}" target="_blank" rel="noopener noreferrer">{esc(row["title"])}</a>'
        if row.get("url")
        else esc(row["title"])
    )
    return f'<article class="recipe-row" data-recipe-id="{esc(row["id"])}"><h2>{title}</h2>{metadata}</article>'


def build_catalog(root, records, dist):
    from .publish import FORBIDDEN, _page, esc, visible_text

    ordered = sorted(
        records,
        key=lambda r: (
            -(r.get("match", {}).get("total_score") or 0),
            (r.get("title") or "").casefold(),
            r["id"],
        ),
    )
    index = [index_entry(row) for row in ordered]
    atomic_json(dist / "search-index.json", index)
    membership = {axis: defaultdict(list) for axis in AXES}
    for row in ordered:
        for axis, labels in row["categories"].items():
            for label in labels:
                membership[axis][label].append(row["id"])
    fields = "".join(
        f'<label><span class="sr-only">{label}</span><select data-catalog-filter="{key}"><option value="">{label}</option>'
        + "".join(f"<option>{esc(value)}</option>" for value in sorted(membership[axis]))
        + "</select></label>"
        for key, label, axis in [
            ("cuisine", "Cuisine", "cuisine"),
            ("meal_type", "Type", "meal-type"),
            ("protein", "Protein", "protein"),
            ("method", "Method", "method"),
        ]
    )
    fields += (
        '<label><span class="sr-only">Time</span><select data-catalog-filter="time"><option value="">Time</option>'
        + "".join(
            f"<option>{esc(value)}</option>"
            for value in [
                "Under 15 min",
                "Under 30 min",
                "30–45 min",
                "45–60 min",
                "Over 60 min",
                "Unknown",
            ]
        )
        + "</select></label>"
    )
    controls = (
        '<section class="filters" aria-label="Recipe filters"><label class="search"><span class="sr-only">Search recipes</span><input id="catalog-search" type="search" placeholder="Search recipes…"></label>'
        + fields
        + '<label><span class="sr-only">Sort</span><select id="catalog-sort"><option value="default">Default</option><option value="name">Name</option><option value="time">Time</option></select></label><button id="catalog-reset" type="button">Clear</button></section>'
    )
    config = {
        "index_url": "search-index.json",
        "base_url": "",
        "page_size": PAGE_SIZE,
        "initial_page": 1,
    }
    body = (
        '<div class="directory"><h1>My Recipes</h1>'
        + controls
        + f'<div class="catalog-summary"><p id="catalog-count" role="status">{len(index):,} recipes</p><button id="hidden-toggle" type="button" hidden aria-expanded="false" aria-controls="hidden-panel">Hidden (0)</button></div><section id="hidden-panel" hidden aria-label="Hidden recipes"><h2>Hidden recipes</h2><p>Hidden in this browser only.</p><button id="restore-all" type="button">Restore all</button><button id="hidden-close" type="button">Close</button><ul id="hidden-list"></ul></section><div id="hidden-toast" hidden><span role="status" id="hidden-message"></span> <button id="hidden-undo" type="button">Undo</button></div><p class="source-note">Recipe names open the original recipe in a new tab.</p><section class="recipe-directory" id="catalog-results" aria-label="Recipes">'
        + "".join(recipe_card(row) for row in index)
        + '</section><nav id="catalog-pagination" aria-label="Catalog pages">'
        + '</nav><script id="catalog-config" type="application/json">'
        + json.dumps(config)
        + '</script><script defer src="catalog.js"></script></div>'
    )
    document = _page("My Recipes", body)
    if FORBIDDEN.search(visible_text(document)):
        raise ValueError("Forbidden unit on homepage")
    (dist / "index.html").write_text(document)
    manifest = {
        "recipes_published": len(index),
        "recipe_detail_pages": 0,
        "recipes_with_images": 0,
        "categories": {axis: len(groups) for axis, groups in membership.items()},
        "listing_pages": 1,
        "search_index_records": len(index),
        "page_size": PAGE_SIZE,
        "recipe_urls": {r["id"]: r["url"] for r in index},
        "missing_source_urls": [r["id"] for r in index if not r["url"]],
        "membership": membership,
    }
    atomic_json(root / "site/content/catalog-manifest.json", manifest)
    return manifest
