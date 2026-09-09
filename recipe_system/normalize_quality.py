"""Re-extract immutable source bodies and retain explicit cleanup decisions."""

import html
import re

NOISE = re.compile(
    r"^(?:[\s#|\-:]*|advertisement|reply(?: ↓)?|pinterest|facebook|twitter|metric|us|adjust|quantity\s*\|\s*ingredient|add all ingredients to list|flag if inappropriate|on sale|find me|ok|or|print|save|share|subscribe|必须配料|可选配料|配料|材料|必备原料和工具|ingredients?|instructions?|directions?|method|nutrition facts|reviews?|comments?)$",
    re.IGNORECASE,
)
META = re.compile(
    r"^(?:original recipe yields|note: recipe directions|what.s on sale|\{\{|servings\s+\d+\s+cals|copyright|all rights reserved|jump to recipe|see more|read more)",
    re.IGNORECASE,
)
DURATION = re.compile(
    r"(?:(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h|小时|小時))?\s*(?:(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m|分钟|分鐘))?",
    re.IGNORECASE,
)


def duration(value):
    match = DURATION.fullmatch(value.strip())
    if match and (match[1] or match[2]):
        return float(match[1] or 0) * 60 + float(match[2] or 0)
    return None


def labelled_times(text):
    labels = {
        "active_minutes": r"active(?: cooking)? time|hands.on time",
        "total_minutes": r"total(?: cooking)? time|ready in",
        "prep_minutes": r"prep(?:aration)?(?: time)?",
        "cook_minutes": r"cook(?:ing)? time",
    }
    found = {}
    plain = html.unescape(re.sub(r"<[^>]+>", " ", text))
    lines = [line.strip().strip("#*_ ") for line in plain.splitlines()]
    for field, label in labels.items():
        pattern = re.compile(rf"^(?:{label})[ :*_]*(.*)$", re.IGNORECASE)
        for index, line in enumerate(lines):
            match = pattern.match(line)
            if not match:
                continue
            candidate = match[1].strip()
            if not candidate:
                candidate = next((part for part in lines[index + 1 : index + 4] if part), "")
            value = duration(candidate.strip("*_ ."))
            if value is not None and value > 0:
                found[field] = value
                break
    return found


def reextract(raw):
    from .recipes import parse_content

    result = dict(raw)
    issues, decisions = [], []
    body = raw.get("raw_text")
    if body:
        source_key = raw["source"].split("github.com/")[-1].replace("/", "--")
        path = raw.get("archive_parse_path") or source_key + "/" + raw.get("source_path", "")
        try:
            parsed = parse_content(body, path)
            position = raw.get(
                "archive_member_position",
                int(str(raw.get("source_recipe_id", "#0")).rsplit("#", 1)[-1]),
            )
            if (
                position < len(parsed)
                and parsed[position].get("ingredients")
                and parsed[position].get("instructions")
            ):
                for key in [
                    "title",
                    "ingredients",
                    "instructions",
                    "cuisine",
                    "tags",
                    "servings",
                    "equipment",
                    "nutrition",
                    "timing",
                ]:
                    if parsed[position].get(key) is not None:
                        result[key] = parsed[position][key]
                result["extraction_method"] = "immutable-source-body-layout-v1"
            else:
                issues.append("source body could not be confidently re-extracted")
        except (ValueError, TypeError, IndexError, KeyError):
            issues.append("source body re-extraction failed")
        timing = dict(result.get("timing") or {})
        for field, value in labelled_times(body).items():
            if timing.get(field) is None:
                timing[field] = value
        result["timing"] = timing
    for field in ["ingredients", "instructions"]:
        cleaned = []
        for position, text in enumerate(result.get(field, [])):
            value = html.unescape(str(text)).strip()
            if NOISE.fullmatch(value) or META.match(value):
                decisions.append(
                    {
                        "field": field,
                        "position": position,
                        "original_text": text,
                        "reason": "structural/navigation fragment",
                    }
                )
                continue
            if field == "ingredients" and "|" in value:
                cells = [part.strip() for part in value.strip("|").split("|") if part.strip()]
                if len(cells) == 2 and re.match(r"^[\d.½¼¾⅓⅔]", cells[0]):
                    value = " ".join(cells)
                    decisions.append(
                        {
                            "field": field,
                            "position": position,
                            "original_text": text,
                            "reason": "quantity/ingredient table cells joined",
                        }
                    )
            cleaned.append(value)
        result[field] = cleaned
    return result, issues, decisions


def timing_consistency(instructions, total_minutes):
    """Explicit action durations are lower bounds, never inferred active times."""
    from .normalize import NUMBER, number

    findings = []
    action = re.compile(
        r"(?i)\b(?:marinate|refrigerate|chill|rest|soak|ferment|proof|simmer|bake|cook|roast|freeze|leave|set aside|saute|sauté|prepare|make)\b|炖|煮|蒸|烤|腌|静置|冷藏"
    )
    amounts = re.compile(
        rf"(?<![\d./])({NUMBER})(?:\s*(?:-|–|to)\s*{NUMBER})?\s*(minutes?|mins?|hours?|hrs?|days?|分钟|小时|天)(?![A-Za-z])",
        re.IGNORECASE,
    )
    for index, step in enumerate(instructions):
        if re.search(r"(?i)\b(?:leftovers?|store|storage|keeps? for|lasts? for)\b", step):
            continue
        if not action.search(step):
            continue
        for match in amounts.finditer(step):
            unit = match[2].lower()
            multiplier = (
                1440
                if unit.startswith("day") or unit == "天"
                else 60
                if unit.startswith(("hour", "hr")) or unit == "小时"
                else 1
            )
            amount = number(match[1]) * multiplier
            findings.append(
                {"instruction_index": index, "minimum_minutes": amount, "source_duration": match[0]}
            )
    lower_bound = max((f["minimum_minutes"] for f in findings), default=None)
    issues = []
    if total_minutes is not None and lower_bound is not None and lower_bound > total_minutes:
        issues.append("explicit instruction duration exceeds stated total time")
    advance = any(f["minimum_minutes"] >= 1440 for f in findings)
    if advance:
        issues.append("instructions require advance preparation of at least one day")
    return {
        "step_time_lower_bound_minutes": lower_bound,
        "requires_advance_preparation": advance,
        "timing_evidence": findings,
    }, issues
