"""Conservative layout adapters, used only when the original parser fails.

Evidence is structural: ingredient headings/tables or a contiguous measured
list, followed by explicit directions or cooking verbs. No recipe facts added.
"""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser

ACTION = re.compile(
    r"^(?:\d+[.)]\s*)?(?:(?:in (?:a|the) [^,]+,?\s+)?(?:preheat|heat|mix|combine|add|put|place)|salt|dice|cube|start|take|throw|transfer|grease|shape|use|stir|whisk|beat|cream|bake|cook|cut|chop|slice|serve|pour|melt|wash|bring|remove|cover|fold|knead|blend|toss|season|marinate|drain|fry|spread|roll|let|allow|form|sift|press|line|rinse|pat|rub|set|prepare|boil|grill|roast|peel|saute|sauté)\b",
    re.IGNORECASE,
)
MEASURED = re.compile(
    r"^(?:[-*+]\s+)?(?:[0-9¼½¾⅓⅔⅛⅜⅝⅞]|one\b|two\b|three\b|half\b|quarter\b)", re.IGNORECASE
)
INGREDIENT_HEADING = re.compile(
    r"^(?:(?:recipe|sauce|custom|main|all|the)\s+)?ingredients?\b|^(?:材料|食材|原料|Zutaten|Ingredienser|Ingrédients|Ingredientes)(?:\s|:|$)",
    re.IGNORECASE,
)
METHOD_HEADING = re.compile(
    r"^(?:instructions?|directions?|method|preparation|procedure|cooking|how to make(?: it)?|how to cook|making\b|recipe customization|操作|做法|步骤|制作|Zubereitung|Tillagning|Préparation|Preparación)(?:\b|:|$)",
    re.IGNORECASE,
)
STOP = re.compile(
    r"^(?:(?:\d+\s+)?comments?\b|recipe notes?\b|notes?\s*:|leave a (?:reply|comment)|you may also like|related recipes|share this|rate this recipe|did you make|tags:|forked from|source:|contributed by|footnotes|references|reviews?\b|reply\b|copyright\b|©|all rights reserved|all recipes are listed|sign up|about us|related posts|loading\.\.|photo by|used in this recipe|most recent|most popular|close$|share this|you might also|nutrition(?:al)?(?: information| facts| info)?\b)",
    re.IGNORECASE,
)


def clean(line):
    return re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", line.strip()).strip()


def label(line):
    return re.sub(r"^[#*_\s]+|[*_:]+$", "", line.strip()).strip()


def recover_markdown(text, path, *, archive=False):
    from .recipes import markdown

    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\xa0", " ")
    lines = text.splitlines()
    # Multiple recipe cards need a title-aware partition adapter; never combine
    # ingredients across independent dishes or silently retain only card one.
    if archive and (
        sum(bool(INGREDIENT_HEADING.match(label(line))) for line in lines) > 1
        and sum(bool(METHOD_HEADING.match(label(line))) for line in lines) > 1
        or archive
        and len(re.findall(r"(?im)^why this recipe works\b", text)) > 1
    ):
        return []
    record = markdown("# " + path.rsplit("/", 1)[-1].rsplit(".", 1)[0], path)[0]
    title = re.search(r"(?m)^#\s+(.+)$|^([^\n]+)\n=+\s*$", text)
    if title:
        record["title"] = next(x for x in title.groups() if x)
    if archive:
        record["original_url"] = (
            lines[0].strip() if lines and lines[0].startswith(("http://", "https://")) else None
        )
        if record["original_url"]:
            record["title"] = (
                record["original_url"]
                .rstrip("/")
                .rsplit("/", 1)[-1]
                .replace("-", " ")
                .replace("_", " ")
            )
            record["title_method"] = "source-url-slug (original page heading unavailable)"
    # Start at explicit heading/table, otherwise only at >=3 contiguous measured
    # lines (blank lines allowed). This excludes lists of navigation links.
    start = None
    explicit_start = False
    for i, line in enumerate(lines):
        if INGREDIENT_HEADING.match(label(line)) or re.match(
            r"^\|?\s*Quantity\s*\|\s*Ingredient", line, re.IGNORECASE
        ):
            start = i + 1
            explicit_start = True
            break
    if start is None:
        for i, line in enumerate(lines):
            if not MEASURED.match(line.strip()) or len(line) > 180:
                continue
            upcoming = [x for x in lines[i:] if x.strip()][:3]
            if len(upcoming) == 3 and all(
                MEASURED.match(x.strip()) and len(x) < 180 for x in upcoming
            ):
                start = i
                break
    if start is None and not archive:
        for i, line in enumerate(lines):
            upcoming = [x for x in lines[i:] if x.strip()][:2]
            if len(upcoming) == 2 and all(re.match(r"^\s*[-*+]\s+[^[]", x) for x in upcoming):
                start = i
                break
    if start is None:
        return []
    ingredients = []
    instructions = []
    mode = "ingredients"
    skip_nutrition = False
    blank_before = True
    ignored = re.compile(
        r"^(?:advertisement|advertising|on sale|find me|add all ingredients to list|add to shopping list|check all|uncheck all|print|save|pin|facebook|pinterest|twitter|email|share|nutrition|prep|cook|ready in|\d+\s*[mh])\s*[:!]*$",
        re.IGNORECASE,
    )
    for line in lines[start:]:
        value = clean(line)
        heading = label(line)
        if not value:
            blank_before = True
            continue
        separated = blank_before
        blank_before = False
        if ignored.fullmatch(value):
            continue
        if mode == "ingredients" and re.match(
            r"^(?:yield|makes:|servings|serves|nutrition|note, these instructions|\d+ made this|us metric|units$)",
            value,
            re.IGNORECASE,
        ):
            continue
        if (
            mode == "instructions"
            and archive
            and (line.strip().startswith("[") or re.fullmatch(r"-{10,}", value))
        ):
            break
        if re.fullmatch(r"\d+[.)]", value):
            continue
        if (
            value in ["[]"]
            or re.fullmatch(r"[| :\-=]+", value)
            or line.strip().startswith(("![", "<!--"))
        ):
            continue
        if METHOD_HEADING.match(heading) or (
            ingredients and re.match(r"^Step\s+\d+\b", heading, re.IGNORECASE)
        ):
            mode = "instructions"
            skip_nutrition = False
            continue
        if STOP.match(heading):
            if re.match("nutrition", heading, re.IGNORECASE) and not instructions:
                skip_nutrition = True
                continue
            break
        if skip_nutrition:
            continue
        if INGREDIENT_HEADING.match(heading):
            mode = "ingredients"
            continue
        if re.match(r"^\|?\s*Quantity\s*\|\s*Ingredient", line, re.IGNORECASE):
            mode = "ingredients"
            continue
        if line.strip().startswith("#"):
            continue
        if (
            mode == "ingredients"
            and ingredients
            and ACTION.match(value)
            and (separated or re.match(r"^[-*+]\s+", line))
        ):
            mode = "instructions"
        if mode == "instructions" and MEASURED.match(value) and re.match(r"^[-*+]\s+", line):
            ingredients.append(value)
            continue
        if mode == "ingredients":
            if value.startswith("[") and value.endswith("]"):
                continue
            if "|" in value:
                value = " ".join(
                    cell.strip() for cell in value.strip("|").split("|") if cell.strip()
                )
            # Continuation lines are joined, preserving words without treating
            # wrapped prose as independent ingredient quantities.
            if (
                ingredients
                and not MEASURED.match(value)
                and (
                    not separated
                    or re.fullmatch(
                        r"[\d\s/.,¼½¾]+(?:pkg\.?|cups?\.?|g|kg|oz|lb)?",
                        ingredients[-1],
                        re.IGNORECASE,
                    )
                )
                and not re.match(r"^\s*[-*+]\s+", line)
            ):
                ingredients[-1] += " " + value
            else:
                ingredients.append(value)
        elif mode == "instructions":
            instructions.append(value)
    if not ingredients or not instructions:
        return []
    if archive and any(len(x) > 200 for x in ingredients):
        return []
    if not explicit_start and any(len(x) > 260 for x in ingredients):
        return []
    if re.search(r"README-(?:FR|CN|SV|ES)", path, re.IGNORECASE) and not any(
        METHOD_HEADING.match(label(x)) for x in lines
    ):
        return []
    # Unlabelled archives must have cooking evidence, not numbered comments.
    if archive and not any(ACTION.match(x) for x in instructions):
        return []
    record.update(
        ingredients=ingredients, instructions=instructions, parser_method="layout-recovery-v1"
    )
    return [record]


class RecipeLayout(HTMLParser):
    """Extract explicitly named recipe component classes and RDFa properties."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.ingredients = []
        self.instructions = []
        self.title = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tokens = (
            attrs.get("class", "")
            + " "
            + attrs.get("property", "")
            + " "
            + attrs.get("itemprop", "")
        ).lower()
        kind = None
        if re.search(
            r"(?:^|\s)(?:wprm-recipe-ingredient|tasty-recipes-ingredient|ingredient|ingredients-item|recipe-ingredient|recipeingredient)(?:\s|$)",
            tokens,
        ):
            kind = "ingredient"
        if re.search(
            r"(?:^|\s)(?:wprm-recipe-instruction-text|tasty-recipes-instructions|instruction|instruction-step|recipe-instruction|recipeinstructions)(?:\s|$)",
            tokens,
        ):
            kind = "instruction"
        self.stack.append({"tag": tag, "text": [], "kind": kind})
        if tag in ["meta", "link", "img", "br", "hr", "input", "source", "wbr"]:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]["text"].append(data)

    def handle_endtag(self, tag):
        indexes = [i for i, f in enumerate(self.stack) if f["tag"] == tag]
        if not indexes:
            return
        while len(self.stack) > indexes[-1]:
            f = self.stack.pop()
            value = " ".join(" ".join(f["text"]).split())
            if f["kind"] == "ingredient" and value:
                self.ingredients.append(value)
            if f["kind"] == "instruction" and value:
                self.instructions.append(value)
            if f["tag"] == "title":
                self.title = value
            if self.stack:
                self.stack[-1]["text"].append(value)

    def records(self):
        from .recipes import structured

        if not self.title or not self.ingredients or not self.instructions:
            return []
        return [
            dict(
                structured(
                    {
                        "name": self.title,
                        "ingredients": self.ingredients,
                        "instructions": self.instructions,
                    }
                ),
                parser_method="explicit-html-components-v1",
            )
        ]
