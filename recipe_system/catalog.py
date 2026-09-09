"""Static, complete catalog views over persisted unique recipes; no ranking changes."""

import hashlib
import json
import math
import re
from collections import defaultdict

from .core import atomic_json

PAGE_SIZE = 48
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


def slug(value):
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return cleaned or "category-" + hashlib.sha256(value.encode()).hexdigest()[:12]


def recipe_url(identifier):
    name = (
        identifier
        if re.fullmatch(r"[A-Za-z0-9_-]+", identifier)
        else "recipe-" + hashlib.sha256(identifier.encode()).hexdigest()[:24]
    )
    return "recipes/" + name + ".html"


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
    match = row.get("match", {})
    cats = row["categories"]
    return {
        "id": row["id"],
        "url": row["url"],
        "title": display_title(row.get("title")),
        "sort_title": display_title(row.get("title")).casefold(),
        "cuisine": ", ".join(cats["cuisine"]),
        "cuisines": cats["cuisine"],
        "meal_type": cats["meal-type"][0],
        "proteins": cats["protein"],
        "methods": cats["method"],
        "time_categories": cats["time"],
        "total_minutes": row.get("total_minutes"),
        "active_minutes": row.get("active_minutes"),
        "coverage": match.get("foodlion_coverage"),
        "ingredients": [
            i["canonical_ingredient"]
            for i in row.get("ingredients", [])
            if i.get("canonical_ingredient")
        ],
        "image": row.get("image"),
    }


def image_html(image, prefix="", thumbnail=False):
    from .publish import _url, esc

    if not image or _url(image.get("url")) == "#":
        return ""
    size = (
        ' class="recipe-thumbnail" width="120" height="90"'
        if thumbnail
        else ' class="recipe-image"'
    )
    photo = f'<img src="{esc(image["url"])}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer"{size}>'
    if thumbnail:
        return f'<figure class="card-image">{photo}<figcaption>{esc(image.get("attribution") or "")}</figcaption></figure>'
    return f'<figure>{photo}<figcaption>{esc(image.get("attribution") or "")} <a href="{esc(_url(image.get("source_url")))}">Image source</a> · {esc(image.get("license") or "Permission recorded")}</figcaption></figure>'


def recipe_card(row, prefix=""):
    """Shared compact recipe card; no recommendation information is published."""
    from .publish import esc

    facts = cooking_facts(row)
    metadata = f'<p class="card-meta">{esc(facts)}</p>' if facts else ""
    return f'<article class="card recipe-card" data-recipe-id="{esc(row["id"])}"><h2><a href="{esc(prefix + row["url"])}">{esc(row["title"])}</a></h2>{image_html(row.get("image"), thumbnail=True)}{metadata}</article>'


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
    pages = max(1, math.ceil(len(index) / PAGE_SIZE))
    fields = "".join(
        f'<label>{label}<select data-catalog-filter="{key}"><option value="">All</option>'
        + "".join(f"<option>{esc(value)}</option>" for value in sorted(membership[axis]))
        + "</select></label>"
        for key, label, axis in [
            ("cuisine", "Cuisine", "cuisine"),
            ("meal_type", "Meal Type", "meal-type"),
            ("protein", "Main Protein", "protein"),
            ("method", "Cooking Method", "method"),
        ]
    )
    fields += (
        '<label>Total Time<select data-catalog-filter="time"><option value="">Any time</option>'
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
    fields += '<label>Food Lion Compatibility<select data-catalog-filter="coverage"><option value="">Any</option><option value="95">Highest compatibility</option><option value="85">High compatibility</option><option value="70">Good compatibility</option></select></label>'
    controls = (
        '<section class="filters" aria-label="Recipe filters"><label class="search"><span class="sr-only">Search recipes</span><input id="catalog-search" type="search" placeholder="Search recipes…"></label>'
        + fields
        + '<label>Sort<select id="catalog-sort"><option value="default">Default</option><option value="name">Recipe Name</option><option value="time">Total Time</option><option value="coverage">Food Lion Compatibility</option></select></label><button id="catalog-reset" type="button">Clear filters</button></section>'
    )
    for number in range(1, pages + 1):
        path = "index.html" if number == 1 else f"page-{number}.html"
        links = []

        def link(n, label, current=number):
            href = "index.html" if n == 1 else f"page-{n}.html"
            return (
                f'<a href="{href}"'
                + (' aria-current="page"' if n == current else "")
                + f">{label}</a>"
            )

        if number > 1:
            links.append(link(number - 1, "Previous"))
        shown = sorted({1, pages} | set(range(max(1, number - 2), min(pages, number + 2) + 1)))
        previous = 0
        for n in shown:
            if previous and n > previous + 1:
                links.append("<span>…</span>")
            links.append(link(n, str(n)))
            previous = n
        if number < pages:
            links.append(link(number + 1, "Next"))
        config = {
            "index_url": "search-index.json",
            "base_url": "",
            "page_size": PAGE_SIZE,
            "initial_page": number,
        }
        body = (
            "<h1>My Recipes</h1>"
            + controls
            + f'<p id="catalog-count" role="status">{len(index):,} recipes</p><section class="cards" id="catalog-results">'
            + "".join(
                recipe_card(row) for row in index[(number - 1) * PAGE_SIZE : number * PAGE_SIZE]
            )
            + '</section><nav id="catalog-pagination" aria-label="Catalog pages">'
            + " ".join(links)
            + '</nav><script id="catalog-config" type="application/json">'
            + json.dumps(config)
            + '</script><script defer src="catalog.js"></script>'
        )
        document = _page("My Recipes", body)
        if FORBIDDEN.search(visible_text(document)):
            raise ValueError("Forbidden unit on " + path)
        (dist / path).write_text(document)
    manifest = {
        "recipes_published": len(index),
        "recipe_detail_pages": len(index),
        "recipes_with_images": sum(bool(r["image"]) for r in index),
        "categories": {axis: len(groups) for axis, groups in membership.items()},
        "listing_pages": pages,
        "search_index_records": len(index),
        "page_size": PAGE_SIZE,
        "recipe_urls": {r["id"]: r["url"] for r in index},
        "membership": membership,
    }
    atomic_json(root / "site/content/catalog-manifest.json", manifest)
    return manifest
