"""Practical meal classification from ingredient structure, never fabricated nutrition."""

import re

from .meal_quality import meal_signals

STAPLES = {
    "rice",
    "brown rice",
    "pasta",
    "bread",
    "potato",
    "sweet potato",
    "quinoa",
    "oats",
    "noodles",
    "tortilla",
    "couscous",
    "barley",
    "bulgur",
}
TYPES = [
    ("Sandwich", r"\b(sandwich|burger|wrap|taco|burrito|quesadilla|banh mi)\b|三明治|汉堡"),
    (
        "Soup/stew",
        r"\b(soup|stew|chili(?! (?:pepper|flakes|powder))|chowder|gumbo|dal|dahl)\b|汤|炖",
    ),
    ("Salad", r"\bsalad\b|沙拉"),
    (
        "Pasta",
        r"\b(pasta|spaghetti|lasagn\w*|linguine|rigatoni|macaroni|penne|noodles?|fettuccine|gnocchi)\b|面条|拌面",
    ),
    ("Rice/grain", r"\b(rice|risotto|quinoa|grain bowl|pilaf)\b|炒饭|盖饭"),
    ("Breakfast", r"\b(breakfast|pancake|waffle|omelet|omelette|porridge|oatmeal)\b"),
    ("Snack", r"\b(sausage balls|cheese balls|snack|popcorn|chips|nachos|trail mix|energy bar)\b"),
]


def practical_signals(recipe, aliases, rules, preferences):
    signals = meal_signals(recipe, aliases, rules)
    names = {i["canonical_ingredient"] for i in recipe["ingredients"]}
    entries = aliases.get("ingredients", {})
    staples = sorted(
        n for n in names if n in STAPLES or entries.get(n, {}).get("category") == "grain"
    )
    protein, vegetables = signals["protein_ingredients"], signals["vegetable_ingredients"]
    role = signals["meal_role"]
    title = recipe.get("title", "").replace("_", " ")
    ingredient_text = " ".join(names).lower()
    savory_core = any(
        entries.get(n, {}).get("category") in {"meat", "seafood", "legume"} for n in names
    )
    sweet_base = bool(re.search(r"sugar|syrup|糖", ingredient_text)) and bool(
        re.search(r"flour|面粉", ingredient_text)
    )
    sweet_flavor = bool(
        re.search(r"vanilla|chocolate|cocoa|cinnamon|icing|raisins|香草|巧克力", ingredient_text)
    )
    strong_dessert = re.search(rules["roles"]["dessert"], title) or re.search(
        r"snickerdoodle|fruit pizza|pumpkin pie|dutch baby", title, re.IGNORECASE
    )
    savory_cake = re.search(r"fish cakes?|crab cakes?|rice cakes?", title, re.IGNORECASE)
    if (strong_dessert and not savory_cake) or (sweet_base and sweet_flavor and not savory_core):
        role = "dessert"
    if re.search(r"mixins|mix.ins|toppings|taco seasoning", title, re.IGNORECASE):
        role = "component"
    excluded = {
        "dessert": "Dessert",
        "condiment": "Sauce/condiment",
        "drink": "Snack",
        "bread": "Baking",
        "component": "Side dish",
        "side": "Side dish",
    }
    meal_type = excluded.get(role)
    if not meal_type:
        meal_type = next(
            (
                label
                for label, pattern in TYPES
                if re.search(pattern, recipe.get("title", ""), re.IGNORECASE)
            ),
            None,
        )
    if not meal_type:
        meal_type = (
            "Full meal"
            if protein and vegetables and staples
            else "Main dish"
            if protein
            else "Side dish"
        )
    if set(protein) == {"egg"} and not vegetables and meal_type == "Main dish":
        meal_type = "Breakfast"
    methods = set(recipe.get("cooking_method", []))
    for method, pattern in [
        ("one-pan", r"\bone.pan\b"),
        ("one-pot", r"\bone.pot\b"),
        ("sheet-pan", r"\bsheet.pan\b"),
        ("air fryer", r"\bair.fr(?:yer|ied)\b"),
    ]:
        if re.search(pattern, title, re.IGNORECASE):
            methods.add(method)
    text = " ".join(recipe.get("instructions", []))
    if meal_type in {"Salad", "Sandwich"} and not re.search(
        r"\b(bake|fry|boil|simmer|roast|grill|cook|heat)\b", text, re.IGNORECASE
    ):
        methods.add("no-cook")
    operations = len(
        re.findall(
            r"\b(?:chop|dice|mince|peel|grate|slice|whisk|beat|roll|fold|wrap|stuff|shape|knead|dredge|drain|brown|saute|mix|stir|fry|frying)\b|切碎|切片|切丁|搅拌|揉面|擀|包入",
            text,
            re.IGNORECASE,
        )
    )
    labor = bool(
        re.search(
            r"deep.fry|deep.fried|knead|dredge|breading|continue rolling|fill.{0,40}wrapper|working in batches|wrap each|roll up|封口|揉|擀|面团|包入|包成",
            text,
            re.IGNORECASE,
        )
    )
    vessels = sorted(
        set(
            re.findall(
                r"\b(?:skillet|saucepan|pot|bowl|baking sheet|wok|frying pan|pan)\b",
                text,
                re.IGNORECASE,
            )
        )
    )
    additional_vessels = len(
        re.findall(
            r"\b(?:another|separate|second)\s+(?:small |large |mixing )?(?:pot|skillet|pan|bowl)\b",
            text,
            re.IGNORECASE,
        )
    )
    vessel_count = len(vessels) + additional_vessels
    duration_bounds = []
    advance = False
    for sentence in re.split(r"[.!?。]", text):
        if re.search(r"leftovers?|store|keeps? for|can be kept", sentence, re.IGNORECASE):
            continue
        sentence = re.sub(
            r"\b(one|two|three|four|five|six)\s+(hours?|minutes?)\b",
            lambda m: (
                str({"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}[m[1].lower()])
                + " "
                + m[2]
            ),
            sentence,
            flags=re.IGNORECASE,
        )
        if re.search(
            r"chill|refrigerat|marinat|rest|soak|simmer|cook|bake|roast|proof|rise|冷藏|腌",
            sentence,
            re.IGNORECASE,
        ):
            for match in re.finditer(
                r"(\d+(?:\.\d+)?)\s*(?:[-–]\s*\d+)?\s*(hours?|minutes?)\b", sentence, re.IGNORECASE
            ):
                duration_bounds.append(
                    float(match[1]) * (60 if match[2].lower().startswith("hour") else 1)
                )
            if re.search(r"overnight|few hours|several hours|隔夜", sentence, re.IGNORECASE):
                advance = True
    processed_rows = sum(
        bool(entries.get(i["canonical_ingredient"], {}).get("processed"))
        or bool(
            re.search(
                r"tater.tots?|condensed|cream of .+ soup|instant .+ mix|processed cheese",
                i.get("original_text", i["canonical_ingredient"]),
                re.IGNORECASE,
            )
        )
        for i in recipe["ingredients"]
    )
    timing_issues = ("instructions require advance preparation", "explicit instruction duration")
    structural = [i for i in signals["quality_issues"] if not i.startswith(timing_issues)]
    # A sparse or contaminated extraction is different from merely absent metadata.
    everyday = (
        meal_type
        in {"Full meal", "Main dish", "Sandwich", "Pasta", "Rice/grain", "Soup/stew", "Salad"}
        and bool(protein)
        and not structural
    )
    if re.search(r"dishwasher|dish washer|洗碗机", title + " " + text, re.IGNORECASE):
        everyday = False
    p = preferences["practical"]
    count, steps = len(names), len(recipe.get("instructions", []))
    steps = max(steps, operations)
    active = recipe.get("active_minutes")
    involved = (
        labor
        or steps > p["maximum_moderate_steps"]
        or count > p["maximum_moderate_ingredients"]
        or (active is not None and active > 45)
    )
    easy = (
        steps <= p["maximum_easy_steps"]
        and count <= p["maximum_easy_ingredients"]
        and vessel_count <= 2
        and not labor
        and (active is None or active <= 15)
    )
    effort = "Involved" if involved else "Easy" if easy else "Moderate"
    signals.update(
        vessel_count=vessel_count,
        processed_ingredient_fraction=processed_rows / max(1, len(recipe["ingredients"])),
        preparation_operations=operations,
        labor_intensive=labor,
        vessels=vessels,
        instruction_time_lower_bound=max(duration_bounds, default=0),
        advance_preparation=advance,
        staple_ingredients=staples,
        meal_type=meal_type,
        everyday_eligible=everyday,
        effort_level=effort,
        cooking_method=sorted(methods),
        structural_issues=structural,
    )
    return signals
