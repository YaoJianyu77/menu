"""Layout recovery regression fixtures contain no invented missing facts."""

from recipe_system.recipes import parse_content


def test_archive_recipe_heading_and_footer_bounds():
    result = parse_content(
        "https://example.com/soup\nRecipe Ingredients\n\n200 g beans\n\n100 g tomato\n\n20 mL oil\n\nPreparation\n\nHeat oil.\nAdd beans and tomato.\n\nReviews\nAdvertisement\nReply\n",
        "soup.gz",
    )[0]
    assert result["ingredients"] == ["200 g beans", "100 g tomato", "20 mL oil"]
    assert result["instructions"] == ["Heat oil.", "Add beans and tomato."]
    assert result["timing"]["active_minutes"] is None


def test_unlabelled_measured_list_and_wrapped_ingredient():
    result = parse_content(
        "https://example.com/soup\nIntro\n\n- 200 g white\n  beans\n- 100 g tomato\n- 20 mL oil\n\nHeat oil.\n\nNotes: serve warm.\n",
        "soup.gz",
    )
    # A wrapped first ingredient lacks a three-line measured run: conservative failure.
    assert result == []
    result = parse_content(
        "# Soup\n\n## Ingredients\n- 200 g white\n  beans\n- 20 mL oil\n\n## Cooking\nHeat oil.\n",
        "soup.md",
    )[0]
    assert result["ingredients"][0] == "200 g white beans"


def test_table_without_ingredient_heading():
    result = parse_content(
        "# Soup\n|Quantity|Ingredient|\n|---|---|\n|200 g|beans|\n|20 mL|oil|\n## Instructions\nHeat and combine.\n",
        "soup.md",
    )[0]
    assert result["ingredients"] == ["200 g beans", "20 mL oil"]


def test_explicit_html_component_classes():
    result = parse_content(
        '<title>Soup</title><div class="wprm-recipe-ingredient">200 g beans</div><div class="wprm-recipe-instruction-text">Heat beans.</div>',
        "soup.html",
    )[0]
    assert result["ingredients"] == ["200 g beans"]
    assert result["instructions"] == ["Heat beans."]


def test_navigation_and_incomplete_recipe_not_recovered():
    assert (
        parse_content(
            "https://example.com/collection\nHome\nRecipes\nDinner\nDesserts\n", "index.gz"
        )
        == []
    )
    result = parse_content("# Soup\n## Ingredients\n- 200 g beans\n", "soup.md")
    assert not result or not result[0]["instructions"]


def test_csv_export_preserves_explicit_total_not_active_time():
    result = parse_content(
        "title,ingredients,instructions,totalTime\nSoup,200 g beans,Heat beans.,15\n", "export.csv"
    )[0]
    assert result["timing"] == {"active_minutes": None, "total_minutes": 15}


def test_unmeasured_bullets_are_preserved_without_inventing_quantity():
    result = parse_content("# Salsa\n* Tomato\n* Onion\n\nChop and combine.\n", "salsa.md")[0]
    assert result["ingredients"] == ["Tomato", "Onion"]
    assert result["instructions"] == ["Chop and combine."]


def test_failure_triage_requires_positive_nonrecipe_evidence():
    from recipe_system.recovery import classify

    assert classify("# Cocoa\n`TODO`", "cocoa.md")[0] == "NOT_A_RECIPE_SOURCE"
    assert classify("https://example.com\n403 Forbidden", "recipe.gz")[0] == "BLOCKED"
    assert classify("https://example.com\nAn unusual narrative.", "recipe.gz")[0] == "UNSUPPORTED"
    assert (
        classify("# Soup\n## Ingredients\n- 200 g beans", "soup.md")[0]
        == "LEGITIMATE_RECIPE_FAILURE"
    )


def test_multiple_json_recipes_remain_separate():
    import json

    payload = [
        {"name": name, "recipeIngredient": [ingredient], "recipeInstructions": ["Heat."]}
        for name, ingredient in [("Beans", "200 g beans"), ("Rice", "100 g rice")]
    ]
    results = parse_content(json.dumps(payload), "recipes.json")
    assert len(results) == 2
    assert results[0]["ingredients"] != results[1]["ingredients"]


def test_archive_members_are_bounded_and_keep_independent_provenance():
    import io
    import json
    import zipfile

    from recipe_system.archives import collect_archive

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "recipe.json",
            json.dumps({"name": "Soup", "ingredients": ["200 g beans"], "instructions": ["Heat."]}),
        )
        archive.writestr("database.json", '{"users": [{"password":"do-not-persist"}]}')
        archive.writestr("../unsafe.json", "{}")
    records, outcomes = collect_archive(stream.getvalue(), parse_content)
    assert len(records) == 1
    assert records[0]["archive_member"] == "recipe.json"
    assert all("do-not-persist" not in str(r) for r in records + outcomes)
    assert {x["status"] for x in outcomes} == {"processed", "unsupported", "failed"}


def test_html_export_cards_never_merge_separate_recipes():
    from recipe_system.archives import export_html

    template = '<div class="recipe"><div id="name">{}</div><li class="recipeIngredient">{}</li><li class="instruction">Heat.</li></div>'
    results = export_html(
        template.format("Beans", "200 g beans") + template.format("Rice", "100 g rice")
    )
    assert [r["title"] for r in results] == ["Beans", "Rice"]
    assert results[0]["ingredients"] == ["200 g beans"]


def test_multiple_explicit_markdown_recipe_cards():
    template = "# {}\n## Ingredients\n- {}\n## Instructions\nHeat.\n"
    results = parse_content(
        template.format("Beans", "200 g beans") + template.format("Rice", "100 g rice"), "meals.md"
    )
    assert [r["title"] for r in results] == ["Beans", "Rice"]
    assert results[0]["ingredients"] == ["200 g beans"]


def test_anonymized_backup_is_not_a_recipe_corpus():
    import io
    import json
    import zipfile

    from recipe_system.archives import collect_archive

    data = {
        "recipes": [{"name": "abcdefghij"}] * 4,
        "recipe_instructions": [{"text": "klmnopqrst"}] * 4,
        "recipes_ingredients": [{"note": "uvwxyzabcd"}] * 4,
        "users": [{"password": "never-persist-this"}],
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("database.json", json.dumps(data))
    records, outcomes = collect_archive(stream.getvalue(), parse_content)
    assert records == []
    assert outcomes[0]["classification"] == "NOT_A_RECIPE_SOURCE"
    assert "never-persist-this" not in str(outcomes)


def test_cookn_tables_join_explicit_recipe_food_and_unit_ids():
    import io
    import zipfile

    from recipe_system.archives import collect_archive

    tables = {
        "temp_recipe.dsv": ("ID||||INSTRUCTIONS||||SERVES", ["r1||||Heat beans.||||2"]),
        "temp_recipe_desc.dsv": ("ID||||TITLE", ["r1||||Bean soup"]),
        "temp_ingredient.dsv": (
            "PARENT_ID||||DISPLAY_ORDER||||INGREDIENT_FOOD_ID||||INGREDIENT_RECIPE_ID||||AMOUNT_UNIT||||AMOUNT_QTY_STRING||||AMOUNT_QTY||||PRE_QUALIFIER||||POST_QUALIFIER",
            ["r1||||0||||f1||||||||u1||||200||||200||||||||"],
        ),
        "temp_food.dsv": ("ID||||NAME", ["f1||||beans"]),
        "temp_unit.dsv": ("ID||||NAME", ["u1||||g"]),
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, (header, rows) in tables.items():
            archive.writestr(name, "!@#%^&*()".join([header, *rows, ""]))
    records, outcomes = collect_archive(stream.getvalue(), parse_content)
    assert len(records) == 1
    assert records[0]["ingredients"] == ["200 g beans"]
    assert records[0]["archive_source_recipe_id"] == "r1"
    assert "source_row_projection" in records[0]["_raw_member_text"]
    assert all(x["status"] == "processed" for x in outcomes)


def test_synthetic_placeholder_requires_all_three_explicit_signals():
    import pytest

    from recipe_system.recipes import SyntheticRecipeError, synthetic_placeholder

    assert synthetic_placeholder("Test Recipe2", "2 itm Test", "Directions.\nWill go here.")
    assert not synthetic_placeholder("Test Recipe", "200 g beans", "Heat beans.")
    with pytest.raises(SyntheticRecipeError):
        parse_content(
            'Title,Ingredients,Directions\nTest Recipe,2 itm Test,"Directions.\nWill go here."\n',
            "recipes.csv",
        )


def test_manifest_distinguishes_accounted_files_from_complete_extraction(tmp_path, monkeypatch):
    from recipe_system.core import atomic_json, atomic_text
    from recipe_system.recipes import RecipeCoordinator

    atomic_text(
        tmp_path / "config/recipe-sources.yaml",
        "sources:\n- id: corpus\n  status: enabled\n  reason: fixture\n  estimated_items: 1\n",
    )
    atomic_json(
        tmp_path / "state/recipes/recipe-agent-01.json",
        {
            "started_at": "2026-09-09T00:00:00-04:00",
            "sources": {"corpus": {"discovered": ["recipe.md"]}},
            "processed": {},
            "failures": {"corpus:recipe.md": {"error_message": "Missing instructions"}},
        },
    )
    monkeypatch.setattr(
        "recipe_system.quality.source_coverage",
        lambda root: {
            "status_counts": {"PARTIAL": 1},
            "sources": [
                {
                    "id": "corpus",
                    "status": "PARTIAL",
                    "unresolved_archive_members": [],
                    "confidently_nonrecipe_failures": 0,
                    "potential_unexplored_candidate_count": 0,
                }
            ],
        },
    )
    result = RecipeCoordinator(tmp_path).manifest()
    assert result["candidate_accounting_complete"] is True
    assert result["sources_accounted"] == 1
    assert result["sources_completed"] == 0
    assert result["completion_status"] == "PARTIAL"
    assert result["completion_timestamp"] is None
    assert result["failures"][0]["error_message"] == "Missing instructions"


def test_git_path_enumeration_preserves_quotes_tabs_and_newlines(tmp_path):
    import subprocess

    from recipe_system.recipes import git_paths

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    paths = ['Recipes/"Mock" Garlic.md', "Recipes/tab\tname.md", "Recipes/line\nbreak.md"]
    (tmp_path / "Recipes").mkdir()
    for path in paths:
        (tmp_path / path).write_text("# Soup\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    assert sorted(git_paths(tmp_path, "HEAD")) == sorted(paths)


def test_archive_placeholder_classification_survives_cli_module_identity():
    import io
    import zipfile

    from recipe_system.archives import collect_archive

    class CommandLinePlaceholderError(ValueError):
        classification = "NOT_A_RECIPE_SOURCE"

    def parser(text, path):
        raise CommandLinePlaceholderError("Explicit placeholder fixture")

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("recipes.csv", "placeholder")
    records, outcomes = collect_archive(stream.getvalue(), parser)
    assert records == []
    assert outcomes[0]["status"] == "excluded"
    assert outcomes[0]["classification"] == "NOT_A_RECIPE_SOURCE"


def test_recovered_audit_distinguishes_old_diagnosis_from_success(tmp_path, monkeypatch):
    from recipe_system.core import atomic_json, read_jsonl, write_jsonl
    from recipe_system.recovery import audit

    directory = tmp_path / "state/recipes/recovery"
    write_jsonl(
        directory / "baseline.jsonl",
        [
            {
                "key": "source:recipe.md",
                "agent": "recipe-agent-01",
                "source_id": "source",
                "revision": "abc",
                "failure": {"item_identifier": "recipe.md", "error_message": "Missing method"},
            }
        ],
    )
    atomic_json(
        tmp_path / "state/recipes/recipe-agent-01.json",
        {"processed": {"source:recipe.md": ["raw-123"]}},
    )
    atomic_json(directory / "summary.json", {"preserved": True})
    monkeypatch.setattr(
        "recipe_system.recovery.content",
        lambda root, row: "# Soup\n## Ingredients\n- 200 g beans\n",
    )
    audit(tmp_path, outcomes_only=True)
    row = read_jsonl(directory / "outcomes.jsonl")[0]
    assert row["classification"] == "RECOVERED"
    assert "raw-123" in row["evidence"]
    assert "cannot both" in row["original_diagnosis"]
    assert row["recovered_raw_ids"] == ["raw-123"]
    assert (directory / "summary.json").read_text().find("preserved") >= 0
