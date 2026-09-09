"""Conservative deterministic ingredient and metric normalization.

US kitchen volumes are rounded culinary conventions (5/15/240 mL).
No volume-to-mass conversion or inferred nutrition/active time.
"""

import html
import json
import re
import unicodedata
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote

from .core import atomic_json, load_yaml, read_jsonl, stable_id, write_jsonl

FORBIDDEN = re.compile(r"\b(?:tsp|tbsp|teaspoons?|tablespoons?)\b", re.IGNORECASE)
UNITS = {
    # Explicit language synonyms use the same configured 5/15 mL kitchen conventions.
    "c. à soupe": (15, "mL"),
    "cuillère à soupe": (15, "mL"),
    "cuillères à soupe": (15, "mL"),
    "c. à café": (5, "mL"),
    "cuillère à café": (5, "mL"),
    "cuillères à café": (5, "mL"),
    "tl": (5, "mL"),
    "teelöffel": (5, "mL"),
    "el": (15, "mL"),
    "esslöffel": (15, "mL"),
    "κ.σ.": (15, "mL"),
    "κ.γ.": (5, "mL"),
    "茶匙": (5, "mL"),
    "汤匙": (15, "mL"),
    "tsp": (5, "mL"),
    "teaspoon": (5, "mL"),
    "teaspoons": (5, "mL"),
    "tbsp": (15, "mL"),
    "tablespoon": (15, "mL"),
    "tablespoons": (15, "mL"),
    "cup": (240, "mL"),
    "cups": (240, "mL"),
    "fl oz": (29.5735, "mL"),
    "fl. oz.": (29.5735, "mL"),
    "fl. oz": (29.5735, "mL"),
    "fluid ounce": (29.5735, "mL"),
    "fluid ounces": (29.5735, "mL"),
    "oz": (28.3495, "g"),
    "ounce": (28.3495, "g"),
    "ounces": (28.3495, "g"),
    "lb": (453.592, "g"),
    "lbs": (453.592, "g"),
    "pound": (453.592, "g"),
    "pounds": (453.592, "g"),
    "pint": (473.176, "mL"),
    "pints": (473.176, "mL"),
    "quart": (946.353, "mL"),
    "quarts": (946.353, "mL"),
    "gallon": (3.78541, "L"),
    "gallons": (3.78541, "L"),
    "g": (1, "g"),
    "gram": (1, "g"),
    "grams": (1, "g"),
    "克": (1, "g"),
    "kg": (1, "kg"),
    "kilogram": (1, "kg"),
    "kilograms": (1, "kg"),
    "千克": (1, "kg"),
    "ml": (1, "mL"),
    "milliliter": (1, "mL"),
    "milliliters": (1, "mL"),
    "毫升": (1, "mL"),
    "l": (1, "L"),
    "liter": (1, "L"),
    "liters": (1, "L"),
    "litre": (1, "L"),
    "litres": (1, "L"),
}
FRACTIONS = {
    "½": "1/2",
    "¼": "1/4",
    "¾": "3/4",
    "⅓": "1/3",
    "⅔": "2/3",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
    "⅕": "1/5",
    "⅖": "2/5",
    "⅗": "3/5",
    "⅘": "4/5",
    "⅙": "1/6",
    "⅚": "5/6",
}
NUMBER = r"(?:\d+\s+\d+/\d+|\d+/\d+|(?:\d+(?:\.\d+)?|\.\d+))"
UNIT_PATTERN = "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))
MEASUREMENT = re.compile(
    rf"(?<![A-Za-z]-)(?<![A-Za-z\d.,/⁄])(?P<q>{NUMBER})(?:\s*(?:-|–|to)\s*(?P<end>{NUMBER}))?(?:\s*-\s*|\s*)(?P<u>{UNIT_PATTERN})(?![A-Za-z0-9_])\.?",
    re.IGNORECASE,
)


def fraction_text(text):
    text = text.replace("⁄", "/").replace("℃", "°C")
    text = re.sub(r"(?<![\d/])(\d+)-(\d+/\d+)", r"\1 \2", text)
    text = re.sub(r"(?<![\d,])(\d+),(\d{1,2})(?![\d,])", r"\1.\2", text)
    for character, value in FRACTIONS.items():
        text = re.sub(rf"(\d){character}", rf"\1 {value}", text)
        text = text.replace(character, value)
    return text


def number(text):
    return float(sum(Fraction(part) for part in text.split()))


def pretty(value):
    return f"{round(value, 3):g}"


def measurement_layout(text):
    """Resolve explicit container notation and missing HTML-boundary whitespace."""
    text = re.sub(
        rf"(?<![\w.]){NUMBER}(?:\s*-\s*|\s*)(?:oz\.?|ounces?)\s+((?:mason |drinking |measuring )?(?:jars?|glasses?|mugs?|bowls?|cups?))\b",
        r"\1 (check source capacity)",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        rf"(?<![\w.])(\d+)\s*[-–]\s*({NUMBER})\s*({UNIT_PATTERN})\.?\s+(cans?|packages?|pkgs?|jars?)\b",
        r"\1 (\2 \3) \4",
        text,
        flags=re.IGNORECASE,
    )
    # Long unit words are unambiguous after a quantity even if HTML lost a space.
    return re.sub(
        rf"(?<![A-Za-z])({NUMBER})\s*((?>tablespoons?|teaspoons?|tbsp|tsp))(?=[A-Za-z])",
        r"\1 \2 ",
        text,
        flags=re.IGNORECASE,
    )


def metric_text(text):
    """Convert all explicit measurements, including within instructions.

    Unquantified forbidden units are labelled metric measures; originals stay raw.
    """
    text = measurement_layout(fraction_text(str(text or "")))

    def replace(match):
        multiplier, unit = UNITS[match["u"].lower()]
        start = pretty(number(match["q"]) * multiplier)
        end = "–" + pretty(number(match["end"]) * multiplier) if match["end"] else ""
        return f"{start}{end} {unit}"

    text = MEASUREMENT.sub(replace, text)
    text = re.sub(
        r"\b((?:\d+(?:\.\d+)?|\.\d+))\s*(?:°\s*F|F|degrees?\s*F(?:ahrenheit)?|Fahrenheit)\b",
        lambda m: f"{pretty((float(m[1]) - 32) * 5 / 9)} °C",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b(?:tablespoons?|tbsp)\b\.?", "15 mL measure", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:teaspoons?|tsp)\b\.?", "5 mL measure", text, flags=re.IGNORECASE)
    return text


def clean_name(text):
    text = unicodedata.normalize("NFKC", text).lower().strip()
    text = re.sub(r"[*_`\[\]]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,-:;")


def canonicalize(text, aliases):
    text = clean_name(text)
    entries = aliases.get("ingredients", aliases)
    lookup = {}
    for canonical, details in entries.items():
        variants = details.get("aliases", []) if isinstance(details, dict) else details
        for alias in [canonical] + list(variants or []):
            lookup[clean_name(alias)] = canonical
    if text in lookup:
        return lookup[text]
    # Only remove explicit preparation suffixes, not ingredient-defining adjectives.
    candidate = re.sub(
        r",\s*(?:chopped|diced|minced|sliced|divided|peeled|to taste|optional)\b.*$", "", text
    )
    candidate = re.sub(r"\s*\((?:optional|to taste)\)\s*", "", candidate)
    candidate = re.sub(r"\s+(?:to taste|as needed)$", "", candidate).strip()
    if candidate in lookup:
        return lookup[candidate]
    prepared = re.sub(
        r"\s*\((?:optional|divided|drained(?: and rinsed)?|finely chopped|chopped|sliced|cooled|at room temperature|to taste)\)\s*",
        " ",
        candidate,
    )
    prepared = re.sub(
        r",?\s+(?:plus more(?: to taste)?|for garnish|roughly chopped|finely chopped|chopped|diced|minced|sliced|grated|divided|drained(?: and rinsed)?)$",
        "",
        prepared,
    ).strip(" ,")
    prepared = re.sub(r"\s+", " ", prepared)
    while True:
        reduced = re.sub(
            r"^(?:(?:finely|roughly|thinly|freshly)\s+)?(?:chopped|minced|diced|sliced|grated|shredded|small|medium|large)\s+",
            "",
            prepared,
        )
        if reduced == prepared:
            break
        prepared = reduced
    prepared = re.sub(r",?\s+(?:softened|melted|at room temperature|to taste)$", "", prepared)
    # Strip only preparation/size descriptors and only to an explicit known alias.
    return lookup.get(prepared, candidate)


def normalize_ingredient(text, aliases):
    original = str(text)
    value = measurement_layout(fraction_text(original)).strip().lstrip("-*• ")
    value = re.sub(r"[*_`]", "", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    measurement = MEASUREMENT.match(value)
    trailing_measurement = False
    if not measurement and not re.match(r"[\d.]", value):
        candidate = MEASUREMENT.search(value)
        if candidate and re.search(r"[\u3400-\u9fff]", value[: candidate.start()]):
            measurement = candidate
            trailing_measurement = True
    quantity = unit = original_quantity = original_unit = quantity_max = None
    name = value
    if measurement:
        original_quantity = measurement["q"]
        original_unit = measurement["u"]
        factor, unit = UNITS[original_unit.lower()]
        quantity = round(number(original_quantity) * factor, 3)
        quantity_max = round(number(measurement["end"]) * factor, 3) if measurement["end"] else None
        name = (
            value[: measurement.start()].strip()
            if trailing_measurement
            else value[measurement.end() :].strip()
        )
        if trailing_measurement:
            name = re.sub(r"的用量为$|用量为$|[：:=]+$", "", name).strip()
            name = re.sub(r"\s*\d+\s*(?:个|根|瓣|片|颗|只|棵|支|条|枚|块)[（(]?$", "", name).strip()
    else:
        count = re.match(rf"^({NUMBER})(?:\s+|(?=[^\W\d_]))", value)
        if count:
            original_quantity = count[1]
            quantity = number(original_quantity)
            name = value[count.end() :].strip()
    chinese_count_unit = None
    if quantity is None:
        chinese_count = re.match(
            r"^(.+?)[ =：:]*?(" + NUMBER + r")\s*(个|根|瓣|片|颗|只|棵|支|条|枚|块)(?:[（(].*)?$",
            value,
        )
        if chinese_count:
            name = chinese_count[1].strip(" =：:")
            original_quantity = chinese_count[2]
            quantity = number(original_quantity)
            chinese_count_unit = chinese_count[3]
    package = None
    package_match = re.match(
        r"^\(\s*("
        + NUMBER
        + r")\s*("
        + UNIT_PATTERN
        + r")\.?\s*\)\s*(cans?|packages?|pkgs?|jars?)\s+(.+)$",
        name,
        re.IGNORECASE,
    )
    if package_match:
        multiplier, package_unit = UNITS[package_match[2].lower()]
        package = {
            "count": quantity,
            "quantity": round(number(package_match[1]) * multiplier, 3),
            "unit": package_unit,
            "container": package_match[3],
            "mass_basis": "package size, not inferred drained weight",
        }
        name = package_match[4]
    count_form = re.match(
        r"^(slices?|cloves?|stalks?|sprigs?|leaves?)\s+(.+)$", name, re.IGNORECASE
    )
    count_unit = count_form[1] if count_form else chinese_count_unit
    if count_form:
        name = count_form[2]
    name = re.sub(r"^of\s+", "", name, flags=re.IGNORECASE)
    canonical = canonicalize(name, aliases)
    # Never allow forbidden original spellings into canonical published fields.
    canonical = metric_text(canonical)
    return {
        "original_text": original,
        "original_quantity": original_quantity,
        "original_unit": original_unit,
        "quantity": quantity,
        "quantity_max": quantity_max,
        "unit": unit,
        "canonical_ingredient": canonical,
        "optional": bool(re.search(r"\boptional\b|可选", original, re.IGNORECASE)),
        "normalization_method": "explicit-alias"
        if canonical in aliases.get("ingredients", {})
        else "unresolved-name",
        "display": metric_text(value),
        "package": package,
        "count_unit": count_unit,
    }


def normalize_servings(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return value
    if isinstance(value, str):
        match = re.fullmatch(
            r"\s*(?:serves?\s*)?(\d+(?:\.\d+)?)(?:\s*(?:servings?|people|portions?))?\s*",
            value,
            re.IGNORECASE,
        )
        if match:
            return float(match[1])
    return None


def normalize_recipe(raw, aliases):
    from .normalize_quality import reextract, timing_consistency

    raw, quality_issues, cleanup = reextract(raw)
    title = raw["title"]
    title_method = raw.get("extraction_method", "source-title")
    ingredients = [normalize_ingredient(value, aliases) for value in raw.get("ingredients", [])]
    meaningful = []
    for index, ingredient in enumerate(ingredients):
        if not ingredient["canonical_ingredient"] or not any(
            c.isalpha() for c in ingredient["canonical_ingredient"]
        ):
            cleanup.append(
                {
                    "field": "ingredients",
                    "position": index,
                    "original_text": ingredient["original_text"],
                    "reason": "quantity without ingredient identity",
                }
            )
        else:
            meaningful.append(ingredient)
    ingredients = meaningful
    entries = aliases.get("ingredients", {})
    proteins = [
        i["canonical_ingredient"]
        for i in ingredients
        if entries.get(i["canonical_ingredient"], {}).get("protein")
    ]
    vegetables = [
        i["canonical_ingredient"]
        for i in ingredients
        if entries.get(i["canonical_ingredient"], {}).get("vegetable")
    ]
    timing = raw.get("timing") or {}
    for field in ["active_minutes", "total_minutes", "prep_minutes", "cook_minutes"]:
        if timing.get(field) is not None and (
            not isinstance(timing[field], (int, float)) or timing[field] <= 0
        ):
            timing[field] = None
    if any(len(i["original_text"]) > 400 for i in ingredients):
        quality_issues.append(
            "ingredient extraction contains unusually long prose; source review required"
        )
    instructions = [metric_text(step) for step in raw.get("instructions", [])]
    explicit = " ".join(
        [raw.get("title", "")] + raw.get("equipment", []) + raw.get("tags", []) + instructions
    ).lower()
    patterns = {
        "air fryer": r"air[ -]fry",
        "oven": r"\boven\b|烤箱",
        "stovetop": r"\bstovetop\b|\bskillet\b|\bfrying pan\b",
        "one-pan": r"\bone[ -]pan\b|\bone[ -]pot\b",
        "sheet-pan": r"\bsheet[ -]pan\b|\bbaking sheet\b",
        "microwave": r"\bmicrowave\b|微波炉",
        "no-cook": r"\bno[ -]cook\b",
    }
    methods = [method for method, pattern in patterns.items() if re.search(pattern, explicit)]
    timing_quality, timing_issues = timing_consistency(instructions, timing.get("total_minutes"))
    quality_issues.extend(timing_issues)
    if (
        len(ingredients) <= 3
        and all(i["quantity"] is None for i in ingredients)
        and len(" ".join(instructions)) > 400
    ):
        quality_issues.append(
            "sparse unquantified ingredient list conflicts with detailed preparation; source review required"
        )
    return {
        "id": raw["id"],
        "raw_id": raw["id"],
        "title": metric_text(html.unescape(re.sub(r"<[^>]+>", "", title))),
        "title_normalization_method": title_method,
        "cuisine": html.unescape(
            re.sub(
                r"<[^>]+>",
                "",
                ", ".join(map(str, raw["cuisine"]))
                if isinstance(raw.get("cuisine"), list)
                else str(raw["cuisine"]),
            )
        )
        if raw.get("cuisine")
        else None,
        "servings": normalize_servings(raw.get("servings")),
        "ingredients": ingredients,
        "instructions": instructions,
        "active_minutes": timing.get("active_minutes"),
        "total_minutes": timing.get("total_minutes"),
        "equipment": raw.get("equipment", []),
        "cooking_method": methods,
        "major_protein": max(
            proteins,
            key=lambda name: (
                max(
                    (
                        i["quantity"] * (1000 if i["unit"] == "kg" else 1)
                        for i in ingredients
                        if i["canonical_ingredient"] == name
                        and i["unit"] in {"g", "kg"}
                        and i["quantity"] is not None
                    ),
                    default=0,
                ),
                {"meat": 5, "seafood": 5, "plant-protein": 4, "legumes": 4, "dairy": 1}.get(
                    entries.get(name, {}).get("category"), 2
                ),
                name,
            ),
        )
        if proteins
        else None,
        "vegetables": sorted(set(vegetables)),
        "tags": [metric_text(t) for t in raw.get("tags", [])],
        "nutrition": raw.get("nutrition"),
        "source": raw["source"],
        "source_url": raw["source_url"],
        "source_path": raw.get("source_path"),
        "archive_member": raw.get("archive_member"),
        "original_source_url": raw.get("original_source_url"),
        "source_license": raw.get("source_license", "unknown"),
        "attribution": raw.get("attribution", raw["source"]),
        "source_revision": raw.get("source_revision"),
        "retrieved_at": raw["retrieved_at"],
        "publication_allowed": raw.get("publication_allowed", False),
        "normalization_version": 2,
        "quality_issues": quality_issues,
        "timing_quality": timing_quality,
        "source_cleanup_decisions": cleanup,
        "prep_minutes": timing.get("prep_minutes"),
        "cook_minutes": timing.get("cook_minutes"),
        "active_time_upper_bound_minutes": timing.get("total_minutes")
        if timing.get("active_minutes") is None
        else timing.get("active_minutes"),
        "normalization_warnings": quality_issues
        + ["Ingredient parsing is conservative; verify unresolved names against source"]
        if any(i["normalization_method"] == "unresolved-name" for i in ingredients)
        else quality_issues,
    }


def normalize_recipes(root):
    root = Path(root)
    aliases = load_yaml(root / "config/ingredient-aliases.yaml")
    records = {}
    for path in sorted((root / "data/recipes/raw").glob("*.jsonl")):
        for raw in read_jsonl(path):
            if raw["id"] in records and records[raw["id"]] != raw:
                raise ValueError(f"Conflicting raw ID: {raw['id']}")
            records[raw["id"]] = raw
    normalized = [normalize_recipe(records[key], aliases) for key in sorted(records)]
    source_config = root / "config/recipe-sources.yaml"
    sources = (
        {item["url"]: item for item in load_yaml(source_config).get("sources", [])}
        if source_config.exists()
        else {}
    )
    for recipe in normalized:
        source = sources.get(recipe["source"], {})
        if source.get("license_path") and recipe.get("source_revision"):
            recipe["source_license_url"] = (
                recipe["source"].rstrip("/")
                + "/blob/"
                + recipe["source_revision"]
                + "/"
                + quote(source["license_path"])
            )
        else:
            recipe["source_license_url"] = None
    write_jsonl(root / "data/recipes/normalized/recipes.jsonl", normalized)
    write_jsonl(
        root / "data/recipes/normalized/quality-issues.jsonl",
        [
            {
                "recipe_id": r["id"],
                "raw_id": r["raw_id"],
                "quality_issues": r["quality_issues"],
                "cleanup_decisions": r["source_cleanup_decisions"],
            }
            for r in normalized
            if r["quality_issues"] or r["source_cleanup_decisions"]
        ],
    )
    return len(normalized)


def fingerprint(recipe):
    # Exact normalized quantities AND instructions: ambiguous variants remain separate.
    return stable_id(
        clean_name(recipe["title"]),
        recipe.get("cuisine"),
        sorted(
            (
                i["canonical_ingredient"],
                str(i.get("quantity")),
                str(i.get("quantity_max")),
                str(i.get("unit")),
                bool(i.get("optional")),
                json.dumps(i.get("package"), sort_keys=True),
                str(i.get("count_unit")),
            )
            for i in recipe["ingredients"]
        ),
        [clean_name(step) for step in recipe["instructions"]],
    )


def deduplicate(root):
    root = Path(root)
    groups = {}
    for recipe in read_jsonl(root / "data/recipes/normalized/recipes.jsonl"):
        groups.setdefault(fingerprint(recipe), []).append(recipe["id"])
    decisions = [
        {
            "fingerprint": key,
            "recipe_ids": sorted(ids),
            "representative_id": min(ids),
            "method": "exact-normalized-content-v2",
        }
        for key, ids in sorted(groups.items())
    ]
    write_jsonl(root / "data/recipes/duplicates/groups.jsonl", decisions)
    atomic_json(
        root / "data/recipes/duplicates/manifest.json",
        {
            "groups": len(groups),
            "duplicate_records": sum(len(ids) - 1 for ids in groups.values()),
            "destructive": False,
        },
    )
    return decisions
