from pathlib import Path

from recipe_system.core import load_yaml
from recipe_system.normalize import canonicalize, clean_name
from recipe_system.quality import candidate_outside_scope, coverage_status


def test_failures_never_establish_source_completeness():
    assert coverage_status("enabled", [], ["failed.md"], []) == "PARTIAL"
    assert coverage_status("enabled", [], [], ["missed.gz"]) == "PARTIAL"
    assert coverage_status("enabled", ["pending.md"], [], []) == "PARTIAL"
    assert coverage_status("enabled", [], [], []) == "COMPLETE"
    assert coverage_status("blocked", [], [], []) == "BLOCKED"
    assert coverage_status("unsupported", [], [], []) == "UNSUPPORTED"
    assert coverage_status("not-a-recipe-source", [], [], []) == "NOT_A_RECIPE_SOURCE"


def test_scope_gap_detection_includes_containers_and_exports():
    assert candidate_outside_scope("src/testing/chocolate_chips.gz")
    assert candidate_outside_scope("tests/data/migrations/chowdown.zip")
    assert candidate_outside_scope("tests/data/migrations/myrecipebox.csv")
    assert candidate_outside_scope("internal/models/testdata/ocr/recipe1.json")
    assert not candidate_outside_scope("frontend/components/RecipeCard.vue")
    assert not candidate_outside_scope("docs/install.md")
    assert not candidate_outside_scope("README.md")


def test_aliases_are_unique_and_preserve_ingredient_distinctions():
    aliases = load_yaml(Path(__file__).resolve().parents[1] / "config/ingredient-aliases.yaml")
    seen = {}
    for canonical, metadata in aliases["ingredients"].items():
        for alias in [canonical, *metadata["aliases"]]:
            key = clean_name(alias)
            assert key not in seen or seen[key] == canonical, (key, canonical, seen.get(key))
            seen[key] = canonical
    for pair in [
        ("chicken breast", "chicken thigh"),
        ("chicken leg", "chicken drumstick"),
        ("light brown sugar", "dark brown sugar"),
        ("soy sauce", "dark soy sauce"),
        ("ground cinnamon", "cinnamon"),
        ("dried oregano", "oregano"),
        ("cooking oil", "olive oil"),
    ]:
        assert canonicalize(pair[0], aliases) != canonicalize(pair[1], aliases)
    assert canonicalize("生抽", aliases) == "soy sauce"
    assert canonicalize("老抽", aliases) == "dark soy sauce"
    assert canonicalize("semi-sweet chocolate chips", aliases) == "semisweet chocolate chips"


def test_unresolved_archive_member_prevents_complete_source(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import yaml

    from recipe_system.core import atomic_json
    from recipe_system.quality import source_coverage

    (tmp_path / "config").mkdir()
    source = {
        "id": "source",
        "url": "https://example.invalid/source",
        "revision": "abc",
        "status": "enabled",
        "reason": "Recipe archive",
        "include": ["*.zip"],
        "estimated_items": 1,
    }
    (tmp_path / "config/recipe-sources.yaml").write_text(
        yaml.safe_dump({"index_revision": "abc", "sources": [source]})
    )
    (tmp_path / ".cache/recipes/source/.git").mkdir(parents=True)
    atomic_json(
        tmp_path / "state/recipes/recipe-agent-01.json",
        {
            "agent": "recipe-agent-01",
            "processed": {"source:recipes.zip": ["recipe-id"]},
            "failures": {},
            "archive_members": {
                "source:recipes.zip": [
                    {
                        "member": "database.json",
                        "status": "unsupported",
                        "reason": "Requires recipe-only joins",
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(
        "recipe_system.quality.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"recipes.zip\0", stderr=b""),
    )
    report = source_coverage(tmp_path)
    row = report["sources"][0]
    assert row["file_accounting_complete"]
    assert not row["extraction_complete"]
    assert row["status"] == "PARTIAL"
    assert row["archive_member_status_counts"] == {"unsupported": 1}


def test_cohorts_do_not_invent_missing_cuisine():
    from recipe_system.quality import select_cohorts

    recipe = {
        "id": "one",
        "title": "Noodles",
        "source": "https://github.com/Anduin2017/HowToCook",
        "source_url": "https://example.invalid/noodles",
        "cuisine": None,
        "total_minutes": 19,
        "ingredients": [{"canonical_ingredient": "rice", "display": "200 g rice"}],
        "instructions": ["Cook."],
    }
    match = {
        "recipe_id": "one",
        "total_score": 65,
        "status": "needs-review",
        "recommendation_status": "recommended-with-caveats",
    }
    cohorts = select_cohorts([recipe], [match])
    assert cohorts["french_top_10"]["available_count"] == 0
    assert cohorts["chinese_asian_top_10"]["items"][0]["cuisine"] is None
    assert (
        cohorts["chinese_asian_top_10"]["items"][0]["cuisine_selection_basis"]["kind"]
        == "source-collection-inference"
    )
    assert cohorts["under_20_minutes_top_10"]["selected_count"] == 1


def test_new_source_failure_audit_resolves_placeholder_archive(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    import yaml

    from recipe_system.core import atomic_json
    from recipe_system.quality import source_coverage

    (tmp_path / "config").mkdir()
    (tmp_path / ".cache/recipes/source/.git").mkdir(parents=True)
    (tmp_path / "config/recipe-sources.yaml").write_text(
        yaml.safe_dump(
            {
                "index_revision": "abc",
                "sources": [
                    {
                        "id": "source",
                        "url": "https://example.invalid/source",
                        "revision": "abc",
                        "status": "enabled",
                        "reason": "Recipe corpus",
                        "include": ["*.zip"],
                        "estimated_items": 1,
                    }
                ],
            }
        )
    )
    atomic_json(
        tmp_path / "state/recipes/recipe-agent-05.json",
        {
            "processed": {},
            "failures": {"source:placeholder.zip": {"message": "No actual cooking content"}},
            "archive_members": {
                "source:placeholder.zip": [{"member": "recipe.json", "status": "failed"}]
            },
        },
    )
    audit = tmp_path / "state/recipes/recovery/new-source-failures.jsonl"
    audit.parent.mkdir()
    audit.write_text(
        json.dumps({"key": "source:placeholder.zip", "classification": "NOT_A_RECIPE_SOURCE"})
        + "\n"
    )
    monkeypatch.setattr(
        "recipe_system.quality.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=b"placeholder.zip\0", stderr=b""
        ),
    )
    source = source_coverage(tmp_path)["sources"][0]
    assert source["status"] == "COMPLETE"
    assert source["confidently_nonrecipe_failures"] == 1
    assert not source["unresolved_archive_members"]
