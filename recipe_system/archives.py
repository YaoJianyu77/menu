"""Bounded recipe-only ZIP imports; never materialize account/configuration data."""

from __future__ import annotations

import gzip
import io
import json
import re
import zipfile
from html.parser import HTMLParser
from pathlib import PurePosixPath

MAX_MEMBERS = 2000
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024


class ExportCards(HTMLParser):
    """Partition explicit export recipe wrappers before parsing individual fields."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.depth = 0
        self.chunks = []
        self.current = []

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "").split()
        if (
            tag == "div"
            and not self.depth
            and any(x in classes for x in ["recipe", "recipe-details"])
        ):
            self.depth = 1
        elif self.depth and tag == "div":
            self.depth += 1
        if self.depth:
            self.current.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self.depth:
            self.current.append("</" + tag + ">")
            if tag == "div":
                self.depth -= 1
                if not self.depth:
                    self.chunks.append("".join(self.current))
                    self.current = []

    def handle_data(self, data):
        if self.depth:
            self.current.append(data)

    def handle_entityref(self, name):
        self.handle_data("&" + name + ";")

    def handle_charref(self, name):
        self.handle_data("&#" + name + ";")


class ExportFields(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        field = attrs.get("itemprop") or attrs.get("id") or ""
        if not field:
            classes = attrs.get("class", "").split()
            field = next((x for x in classes if x in ["recipeIngredient", "instruction"]), "")
        self.stack.append((tag, field, []))
        if tag in ["meta", "img", "br", "hr", "input", "link"]:
            if attrs.get("content"):
                self.stack[-1][2].append(attrs["content"])
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self.stack:
            self.stack[-1][2].append(data)

    def handle_endtag(self, tag):
        indexes = [i for i, x in enumerate(self.stack) if x[0] == tag]
        if not indexes:
            return
        while len(self.stack) > indexes[-1]:
            name, field, parts = self.stack.pop()
            text = "".join(parts).strip()
            if field and text:
                self.fields.setdefault(field, []).append(text)
            if self.stack:
                self.stack[-1][2].append(text + ("\n" if name in ["p", "li", "div"] else " "))


def export_html(text):
    from .recipes import structured

    cards = ExportCards()
    cards.feed(text)
    records = []
    for chunk in cards.chunks:
        parser = ExportFields()
        parser.feed(chunk)
        f = parser.fields
        title = (f.get("name") or [None])[0]
        ingredients = f.get("recipeIngredient") or f.get("recipeIngredients")
        instructions = (
            f.get("instruction") or f.get("recipeDirections") or f.get("recipeInstructions")
        )
        records.append(
            structured(
                {
                    "name": title,
                    "recipeIngredient": ingredients,
                    "recipeInstructions": instructions,
                    "recipeYield": next(iter(f.get("recipeYield", [])), None),
                    "url": next(iter(f.get("original_link", f.get("recipeSource", []))), None),
                }
            )
        )
    return records


def collect_archive(payload, parser, *, prefix="", depth=0):
    if depth > 1:
        raise ValueError("Nested archive depth exceeds two levels")
    records = []
    outcomes = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = sorted(archive.infolist(), key=lambda x: x.filename)
        if len(infos) > MAX_MEMBERS or sum(x.file_size for x in infos) > MAX_TOTAL_BYTES:
            raise ValueError("Archive exceeds configured bounded entry/expanded-size limits")
        joined, join_outcomes, consumed = cookn_records(archive, prefix)
        records.extend(joined)
        outcomes.extend(join_outcomes)
        for info in infos:
            path = prefix + info.filename
            pure = PurePosixPath(info.filename)
            outcome = {
                "member": path,
                "status": "excluded",
                "reason": "Non-recipe asset or directory",
            }
            outcomes.append(outcome)
            if info.is_dir() or info.filename.startswith("__MACOSX/") or pure.name.startswith("."):
                continue
            if pure.is_absolute() or ".." in pure.parts:
                outcome.update(status="failed", reason="Unsafe archive member path")
                continue
            if info.filename in consumed:
                outcome.update(
                    status="processed",
                    reason="Cookn recipe table rows joined through explicit ID references",
                )
                continue
            suffix = pure.suffix.lower()
            if pure.name.lower() == "database.json":
                if info.file_size > MAX_MEMBER_BYTES or info.flag_bits & 1:
                    outcome.update(status="failed", reason="Encrypted or oversized database member")
                    continue
                database = json.loads(archive.read(info))
                if all(
                    isinstance(database.get(table), list)
                    for table in ["recipes", "recipe_instructions", "recipes_ingredients"]
                ):
                    values = (
                        [r.get("name") for r in database["recipes"]]
                        + [r.get("text") for r in database["recipe_instructions"]]
                        + [
                            r.get(k)
                            for r in database["recipes_ingredients"]
                            for k in ["note", "original_text"]
                        ]
                    )
                    values = [v for v in values if v]
                    empty = not database["recipes"]
                    anonymized = len(values) >= 10 and all(
                        isinstance(v, str) and re.fullmatch(r"[a-z]{10}", v) for v in values
                    )
                    if empty or anonymized:
                        outcome.update(
                            status="excluded",
                            classification="NOT_A_RECIPE_SOURCE",
                            recipe_rows=len(database["recipes"]),
                            inspected_recipe_text_fields=len(values),
                            reason="Empty recipe table"
                            if empty
                            else "All recipe names, instructions and ingredient text are randomized ten-letter tokens; erased cooking content, matching source backup anonymizer",
                        )
                        continue
                outcome.update(
                    status="unsupported",
                    reason="Relational backup recipe schema requires explicit joins; account/config payload not persisted",
                )
                continue
            if consumed and suffix == ".dsv":
                outcome.update(
                    status="excluded",
                    reason="Auxiliary Cookn branding/theme/nutrient table; all recipe IDs enumerated from temp_recipe.dsv",
                )
                continue
            if suffix in [".db", ".sqlite", ".sqlite3", ".dsv"]:
                outcome.update(
                    status="unsupported",
                    reason="Relational export needs explicit recipe-only schema joins",
                )
                continue
            if suffix not in [
                ".json",
                ".md",
                ".markdown",
                ".yaml",
                ".yml",
                ".html",
                ".htm",
                ".csv",
                ".paprikarecipe",
                ".zip",
            ]:
                continue
            if info.file_size > MAX_MEMBER_BYTES or info.flag_bits & 1:
                outcome.update(status="failed", reason="Encrypted or oversized recipe member")
                continue
            try:
                data = archive.read(info)
                if suffix == ".zip":
                    nested, nested_outcomes = collect_archive(
                        data, parser, prefix=path + "!", depth=depth + 1
                    )
                    records.extend(nested)
                    outcomes.extend(nested_outcomes)
                    outcome.update(status="processed", records=len(nested))
                    continue
                if suffix == ".paprikarecipe":
                    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                        data = stream.read(MAX_MEMBER_BYTES + 1)
                    if len(data) > MAX_MEMBER_BYTES:
                        raise ValueError("Expanded Paprika member exceeds byte limit")
                text = data.decode("utf-8-sig")
                parse_path = path + ".json" if suffix == ".paprikarecipe" else path
                # Only explicit Recipe payloads are retained. Wrapper metadata is
                # not copied into records even when other keys coexist in JSON.
                parsed = (
                    export_html(text) if suffix in [".html", ".htm"] else parser(text, parse_path)
                )
                if not parsed:
                    raise ValueError("No supported complete recipe structure in member")
                valid = []
                for i, record in enumerate(parsed):
                    if (
                        not record.get("title")
                        or record.get("title") == "None"
                        or not record.get("ingredients")
                        or not record.get("instructions")
                    ):
                        outcomes.append(
                            {
                                "member": path + f"#{i}",
                                "status": "failed",
                                "reason": "Missing explicit title, ingredient or instruction section",
                            }
                        )
                        continue
                    record = dict(
                        record,
                        archive_member=path,
                        archive_member_position=i,
                        _raw_member_text=text,
                        _parse_member_path=parse_path,
                    )
                    valid.append(record)
                records.extend(valid)
                outcome.update(
                    status="processed" if len(valid) == len(parsed) else "partial",
                    records=len(valid),
                )
            except (ValueError, OSError, UnicodeError, zipfile.BadZipFile) as exc:
                if getattr(exc, "classification", None) == "NOT_A_RECIPE_SOURCE":
                    outcome.update(
                        status="excluded", classification="NOT_A_RECIPE_SOURCE", reason=str(exc)
                    )
                else:
                    outcome.update(status="failed", reason=str(exc))
    return records, outcomes


def cookn_records(archive, prefix=""):
    """Join the documented-in-file Cook'n DSV header columns, preserving rows."""
    from .recipes import structured

    required = [
        "temp_recipe.dsv",
        "temp_recipe_desc.dsv",
        "temp_ingredient.dsv",
        "temp_food.dsv",
        "temp_unit.dsv",
    ]
    names = {PurePosixPath(n).name: n for n in archive.namelist() if not n.startswith("__MACOSX/")}
    if not all(n in names for n in required):
        return [], [], set()
    tables = {}
    for name in required:
        info = archive.getinfo(names[name])
        if info.file_size > MAX_MEMBER_BYTES or info.flag_bits & 1:
            raise ValueError("Oversized/encrypted Cookn table")
        encoding = "cp1252" if "cp1252" in names else "utf-8-sig"
        chunks = archive.read(info).decode(encoding).split("!@#%^&*()")
        headers = chunks[0].split("||||")
        rows = []
        for chunk in chunks[1:]:
            if not chunk:
                continue
            fields = chunk.split("||||")
            if len(fields) != len(headers):
                raise ValueError("Cookn DSV row/header width mismatch")
            rows.append(dict(zip(headers, fields, strict=True)))
        tables[name] = rows
    titles = {r["ID"]: r for r in tables["temp_recipe_desc.dsv"]}
    foods = {r["ID"]: r for r in tables["temp_food.dsv"]}
    units = {r["ID"]: r for r in tables["temp_unit.dsv"]}
    records = []
    outcomes = []
    for row in tables["temp_recipe.dsv"]:
        rid = row["ID"]
        member = prefix + names["temp_recipe.dsv"] + "#" + rid
        try:
            ingredient_rows = sorted(
                [r for r in tables["temp_ingredient.dsv"] if r["PARENT_ID"] == rid],
                key=lambda r: float(r["DISPLAY_ORDER"]),
            )
            ingredients = []
            used_foods = {}
            used_units = {}
            for item in ingredient_rows:
                if not item["INGREDIENT_FOOD_ID"] and not item["INGREDIENT_RECIPE_ID"]:
                    continue  # Section/blank rows remain in source_row_projection.
                food = foods.get(item["INGREDIENT_FOOD_ID"])
                if not food:
                    raise ValueError("Cookn ingredient references absent food row")
                used_foods[food["ID"]] = food
                unit = units.get(item["AMOUNT_UNIT"])
                if item["AMOUNT_UNIT"] and not unit:
                    raise ValueError("Cookn ingredient references absent unit row")
                if unit:
                    used_units[unit["ID"]] = unit
                ingredients.append(
                    " ".join(
                        v
                        for v in [
                            item.get("AMOUNT_QTY_STRING") or item.get("AMOUNT_QTY"),
                            unit.get("NAME") if unit else None,
                            item.get("PRE_QUALIFIER"),
                            food["NAME"],
                            item.get("POST_QUALIFIER"),
                        ]
                        if v and v != "[null]"
                    )
                )
            projection = {
                "name": titles[rid]["TITLE"],
                "ingredients": ingredients,
                "instructions": row["INSTRUCTIONS"],
                "servings": row.get("SERVES"),
                "source_row_projection": {
                    "recipe": row,
                    "recipe_description": titles[rid],
                    "ingredients": ingredient_rows,
                    "foods": list(used_foods.values()),
                    "units": list(used_units.values()),
                },
            }
            record = structured(projection)
            if not ingredients or not record["instructions"]:
                raise ValueError("Cookn recipe lacks ingredients/instructions")
            record.update(
                archive_member=member,
                archive_member_position=0,
                archive_source_recipe_id=rid,
                _raw_member_text=json.dumps(projection, ensure_ascii=False, sort_keys=True),
                _parse_member_path=member + ".json",
                parser_method="cookn-explicit-relational-join-v1",
            )
            records.append(record)
            outcomes.append({"member": member, "status": "processed", "records": 1})
        except (ValueError, KeyError) as exc:
            outcomes.append({"member": member, "status": "failed", "reason": str(exc)})
    return records, outcomes, {names[n] for n in required}
