"""Conservative deterministic ingredient and metric normalization.

US kitchen volumes are rounded culinary conventions (5/15/240 mL).
No volume-to-mass conversion or inferred nutrition/active time.
"""

import html
import re
import unicodedata
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote

from .core import atomic_json, load_yaml, read_jsonl, stable_id, write_jsonl

FORBIDDEN = re.compile(r"\b(?:tsp|tbsp|teaspoons?|tablespoons?)\b", re.IGNORECASE)
UNITS = {
    "tsp": (5, "mL"),
    "teaspoon": (5, "mL"),
    "teaspoons": (5, "mL"),
    "tbsp": (15, "mL"),
    "tablespoon": (15, "mL"),
    "tablespoons": (15, "mL"),
    "cup": (240, "mL"),
    "cups": (240, "mL"),
    "fl oz": (29.5735, "mL"),
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
}
NUMBER = r"(?:\d+\s+\d+/\d+|\d+/\d+|(?:\d+(?:\.\d+)?|\.\d+))"
UNIT_PATTERN = "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))
MEASUREMENT = re.compile(
    rf"(?<![\d.,/⁄])(?P<q>{NUMBER})(?:\s*(?:-|–|to)\s*(?P<end>{NUMBER}))?\s*(?P<u>{UNIT_PATTERN})(?![A-Za-z0-9_])\.?",
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


def metric_text(text):
    """Convert all explicit measurements, including within instructions.

    Unquantified forbidden units are labelled metric measures; originals stay raw.
    """
    text = fraction_text(str(text or ""))

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
    return lookup.get(candidate, candidate)


def normalize_ingredient(text, aliases):
    original = str(text)
    value = fraction_text(original).strip().lstrip("-*• ")
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
            name = re.sub(r"的用量为$|用量为$|[：:]$", "", name).strip()
    else:
        count = re.match(rf"^({NUMBER})(?:\s+|(?=[^\W\d_]))", value)
        if count:
            original_quantity = count[1]
            quantity = number(original_quantity)
            name = value[count.end() :].strip()
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
    title = raw["title"]
    title_method = "source-title"
    if str(raw.get("source_path", "")).lower().endswith((".html", ".htm")) and raw.get("raw_text"):
        from .recipes import parse_content

        try:
            parsed = parse_content(raw["raw_text"], raw["source_path"])
            position = int(str(raw.get("source_recipe_id", "#0")).rsplit("#", 1)[-1])
            if position < len(parsed) and parsed[position].get("title"):
                title = parsed[position]["title"]
                title_method = "raw-html-reparse-v3"
        except (ValueError, TypeError, IndexError):
            pass
    ingredients = [normalize_ingredient(value, aliases) for value in raw.get("ingredients", [])]
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
        "major_protein": proteins[0] if proteins else None,
        "vegetables": sorted(set(vegetables)),
        "tags": [metric_text(t) for t in raw.get("tags", [])],
        "nutrition": raw.get("nutrition"),
        "source": raw["source"],
        "source_url": raw["source_url"],
        "source_path": raw.get("source_path"),
        "original_source_url": raw.get("original_source_url"),
        "source_license": raw.get("source_license", "unknown"),
        "attribution": raw.get("attribution", raw["source"]),
        "source_revision": raw.get("source_revision"),
        "retrieved_at": raw["retrieved_at"],
        "publication_allowed": raw.get("publication_allowed", False),
        "normalization_version": 1,
        "normalization_warnings": [
            "Ingredient parsing is conservative; verify unresolved names against source"
        ]
        if any(i["normalization_method"] == "unresolved-name" for i in ingredients)
        else [],
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
            "method": "exact-normalized-content-v1",
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
