"""Static, complete catalog views over persisted unique recipes; no ranking changes."""

import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

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


def index_entry(row):
    match = row.get("match", {})
    cats = row["categories"]
    return {
        "id": row["id"],
        "url": row["url"],
        "title": row.get("title") or "Untitled recipe",
        "sort_title": (row.get("title") or "").casefold(),
        "cuisine": ", ".join(cats["cuisine"]),
        "cuisines": cats["cuisine"],
        "meal_type": cats["meal-type"][0],
        "proteins": cats["protein"],
        "methods": cats["method"],
        "time_categories": cats["time"],
        "total_minutes": row.get("total_minutes"),
        "active_minutes": row.get("active_minutes"),
        "score": match.get("total_score") or 0,
        "coverage": match.get("foodlion_coverage"),
        "ingredients": [
            i["canonical_ingredient"]
            for i in row.get("ingredients", [])
            if i.get("canonical_ingredient")
        ],
        "image": row.get("image"),
        "effort_level": match.get("effort_level", "Unknown"),
        "everyday_eligible": match.get("everyday_eligible", False),
        "recommended": match.get("total_score", 0) >= 60 and match.get("everyday_eligible", False),
        "discovery_representative": match.get("discovery_representative", True),
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
    """One compact card renderer shared by every statically generated listing."""
    from .publish import esc

    time = (
        f"{row['total_minutes']:g} min"
        if isinstance(row.get("total_minutes"), (int, float))
        else "Time unknown"
    )
    coverage = f"{row['coverage']:.0%}" if row.get("coverage") is not None else "Unknown"
    return f'<article class="card recipe-card" data-recipe-id="{esc(row["id"])}">{image_html(row.get("image"), thumbnail=True)}<h2><a href="{esc(prefix + row["url"])}">{esc(row["title"])}</a></h2><p>{esc(row["cuisine"])} · {esc(row["meal_type"])}</p><p>{time} · {esc(", ".join(row["methods"]))}</p><p>Food Lion: {coverage} · <strong>{row["score"]:g}/100</strong></p></article>'


def category_links(row, prefix="../"):
    from .publish import esc

    parts = []
    for axis, labels in row["categories"].items():
        if axis == "time":
            continue
        links = ", ".join(
            f'<a href="{prefix}{axis}/{slug(label)}/index.html">{esc(label)}</a>'
            for label in labels
        )
        parts.append(f"<span>{AXES[axis]}: {links}</span>")
    return (
        '<nav class="recipe-categories" aria-label="Recipe categories">'
        + " · ".join(parts)
        + "</nav>"
    )


def navigation(prefix=""):
    return (
        '<nav class="site-nav" aria-label="Main navigation">'
        + "".join(
            f'<a href="{prefix}{path}">{title}</a>'
            for path, title in [
                ("index.html", "Home"),
                ("recommended/index.html", "Recommended"),
                ("recipes/index.html", "All Recipes"),
            ]
            + [(axis + "/index.html", label) for axis, label in AXES.items()]
        )
        + "</nav>"
    )


def build_catalog(root, records, dist):
    from .publish import FORBIDDEN, _page, esc, visible_text

    index = sorted(
        [index_entry(row) for row in records], key=lambda r: (-r["score"], r["sort_title"], r["id"])
    )
    for rank, row in enumerate(index):
        row["rank"] = rank
    atomic_json(dist / "search-index.json", index)
    membership = {axis: defaultdict(list) for axis in AXES}
    for label in MEALS:
        membership["meal-type"][label] = []
    for label in list(METHODS.values()) + ["Other"]:
        membership["method"][label] = []
    by_id = {r["id"]: r for r in records}
    for entry in index:
        for axis, values in by_id[entry["id"]]["categories"].items():
            for value in values:
                membership[axis][value].append(entry)
    written = []

    def write(path, title, body):
        destination = dist / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        prefix = "../" * (len(Path(path).parts) - 1)
        document = _page(title, navigation(prefix) + body, prefix)
        if FORBIDDEN.search(visible_text(document)):
            raise ValueError("Forbidden unit on " + path)
        destination.write_text(document)
        written.append(path)

    def listing(path, title, rows, scope):
        pages = max(1, math.ceil(len(rows) / PAGE_SIZE))
        for number in range(1, pages + 1):
            target = path if number == 1 else str(Path(path).parent / f"page-{number}.html")
            prefix = "../" * (len(Path(target).parts) - 1)
            config = {
                "index_url": prefix + "search-index.json",
                "base_url": prefix,
                "scope": scope,
                "page_size": PAGE_SIZE,
                "initial_page": number,
            }
            fields = "".join(
                f'<label>{label}<select data-catalog-filter="{key}"><option value="">All</option></select></label>'
                for key, label in [
                    ("cuisine", "Cuisine"),
                    ("meal_type", "Meal type"),
                    ("protein", "Protein"),
                    ("method", "Cooking method"),
                ]
            )
            numeric = "".join(
                f'<label>{label}<input data-catalog-filter="{key}" type="number" min="0" {maximum}></label>'
                for key, label, maximum in [
                    ("min-score", "Minimum score", 'max="100"'),
                    ("max-score", "Maximum score", 'max="100"'),
                    ("coverage", "Minimum Food Lion %", 'max="100"'),
                    ("total", "Maximum total minutes", ""),
                ]
            )
            controls = f'<section class="filters"><label>Search<input id="catalog-search" type="search" placeholder="Title, ingredient, cuisine…"></label>{fields}{numeric}<label>Sort<select id="catalog-sort"><option value="score">Recommendation score</option><option value="coverage">Food Lion compatibility</option><option value="time">Total time</option><option value="name">Recipe name</option></select></label><button id="catalog-reset">Reset</button></section>'
            links = " ".join(
                f'<a href="{"index.html" if n == 1 else "page-" + str(n) + ".html"}" {"aria-current=page" if n == number else ""}>{n}</a>'
                for n in range(1, pages + 1)
            )
            body = (
                f'<h1>{esc(title)}</h1>{controls}<p id="catalog-count" role="status">{len(rows)} recipes</p><section class="cards" id="catalog-results">'
                + "".join(
                    recipe_card(r, prefix)
                    for r in rows[(number - 1) * PAGE_SIZE : number * PAGE_SIZE]
                )
                + f'</section><nav id="catalog-pagination" aria-label="Catalog pages">{links}</nav><script id="catalog-config" type="application/json">{json.dumps(config).replace("<", chr(92) + "u003c")}</script><script defer src="{prefix}catalog.js"></script>'
            )
            write(target, title, body)

    listing("recipes/index.html", "All Recipes", index, {})
    eligible = [r for r in index if r["everyday_eligible"] and r["discovery_representative"]]
    listing("recommended/index.html", "Recommended", eligible, {"recommended": True})
    groups = [
        ("everyday", "Best Everyday Meals", lambda r: r["score"] >= 60, {"score_min": 60}),
        ("90-plus", "90+", lambda r: r["score"] >= 90, {"score_min": 90}),
        ("80-89", "80–89", lambda r: 80 <= r["score"] < 90, {"score_min": 80, "score_max": 89.999}),
        ("70-79", "70–79", lambda r: 70 <= r["score"] < 80, {"score_min": 70, "score_max": 79.999}),
        ("60-69", "60–69", lambda r: 60 <= r["score"] < 70, {"score_min": 60, "score_max": 69.999}),
        (
            "under-30",
            "Under 30 minutes",
            lambda r: r["total_minutes"] is not None and r["total_minutes"] < 30,
            {"max_time": 29.999},
        ),
        ("easy", "Easy / Low Effort", lambda r: r["effort_level"] == "Easy", {"easy": True}),
        (
            "compatible",
            "High Food Lion compatibility",
            lambda r: r["coverage"] is not None and r["coverage"] >= 0.85,
            {"minimum_coverage": 0.85},
        ),
    ]
    recommendation_links = "".join(
        f'<a href="{key}/index.html">{label}</a> ' for key, label, _, _ in groups
    )
    # Section links stay available on the complete Recommended view.
    rp = dist / "recommended/index.html"
    rp.write_text(
        rp.read_text().replace(
            "<h1>Recommended</h1>",
            '<h1>Recommended</h1><nav class="presets">' + recommendation_links + "</nav>",
        )
    )
    for key, label, predicate, scope in groups:
        listing(
            f"recommended/{key}/index.html",
            label,
            [r for r in eligible if predicate(r)],
            {"recommended": True, **scope},
        )
    for axis, groups_by_label in membership.items():
        links = []
        for label, rows in sorted(groups_by_label.items()):
            path = f"{axis}/{slug(label)}/index.html"
            listing(
                path,
                label,
                rows,
                {"axis": {"meal-type": "meal_type"}.get(axis, axis), "value": label},
            )
            links.append(
                f'<li><a href="{slug(label)}/index.html">{esc(label)}</a> ({len(rows)})</li>'
            )
        write(
            axis + "/index.html",
            AXES[axis],
            f'<h1>{AXES[axis]}</h1><ul class="category-list">' + "".join(links) + "</ul>",
        )
    home = (
        "<h1>Your recipe catalog</h1><p>Find an everyday meal or explore all "
        + str(len(index))
        + " recipes.</p>"
    )
    home_groups = [
        (
            "Best everyday meals",
            [r for r in eligible if r["score"] >= 60],
            "recommended/index.html",
        ),
        (
            "Under 30 minutes",
            [r for r in eligible if r["total_minutes"] is not None and r["total_minutes"] < 30],
            "recommended/under-30/index.html",
        ),
        (
            "Air fryer",
            [r for r in eligible if "Air fryer" in r["methods"]],
            "method/air-fryer/index.html",
        ),
        (
            "One-pan / one-pot",
            [r for r in eligible if set(r["methods"]) & {"One-pan", "One-pot", "Sheet-pan"}],
            "method/index.html",
        ),
        (
            "High Food Lion compatibility",
            [r for r in eligible if (r["coverage"] or 0) >= 0.85],
            "recommended/compatible/index.html",
        ),
    ]
    for title, rows, url in home_groups:
        home += (
            f'<section><h2><a href="{url}">{title}</a></h2><div class="cards">'
            + "".join(recipe_card(r) for r in rows[:6])
            + "</div></section>"
        )
    write("index.html", "Home", home)
    manifest = {
        "recipes_published": len(index),
        "recipe_detail_pages": len(index),
        "recipes_with_images": sum(bool(r["image"]) for r in index),
        "categories": {axis: len(groups) for axis, groups in membership.items()},
        "listing_pages": len(written),
        "search_index_records": len(index),
        "page_size": PAGE_SIZE,
        "recipe_urls": {r["id"]: r["url"] for r in index},
        "membership": {
            axis: {label: [r["id"] for r in rows] for label, rows in groups.items()}
            for axis, groups in membership.items()
        },
    }
    atomic_json(root / "site/content/catalog-manifest.json", manifest)
    return manifest
