import json
import subprocess

from recipe_system.core import read_jsonl
from recipe_system.recipes import RecipeSourceAgent, markdown, parse_content


def test_markdown_frontmatter_and_raw_measurement():
    text = "---\ntitle: Beans\ningredients:\n- 2 tbsp olive oil\ninstructions:\n- Warm the beans.\nreadyTime: 20 min\n---\n"
    recipe = markdown(text, "beans.md")[0]
    assert recipe["ingredients"] == ["2 tbsp olive oil"]
    assert recipe["timing"] == {"active_minutes": None, "total_minutes": 20}


def test_markdown_table_and_chinese():
    text = "# Dinner\n|Ingredients|\n|---|\n|1 cup rice|\n### Instructions\n* Cook rice.\n"
    assert markdown(text, "dinner.md")[0]["ingredients"] == ["1 cup rice"]
    chinese = "# 鸡蛋\n## 必备原料和工具\n- 鸡蛋\n## 计算\n- 鸡蛋 2 个\n## 操作\n1. 炒熟。\n"
    assert markdown(chinese, "egg.md")[0]["ingredients"] == ["鸡蛋 2 个"]


def test_jsonld_nested_recipe():
    source = (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@graph": [
                    {
                        "@type": "Recipe",
                        "name": "Rice",
                        "recipeIngredient": ["1 cup rice"],
                        "recipeInstructions": [{"@type": "HowToStep", "text": "Cook."}],
                    }
                ]
            }
        )
        + "</script>"
    )
    assert parse_content(source, "rice.html")[0]["instructions"] == ["Cook."]
    assert parse_content('{"name":"app","dependencies":{}}', "package.json") == []


def test_collection_resume_and_failure_accounting(tmp_path, monkeypatch):
    repo = tmp_path / ".cache/recipes/example"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "rice.md").write_text(
        "# Rice\n## Ingredients\n- 1 cup rice\n## Instructions\n1. Cook.\n"
    )
    (repo / "beans.md").write_text("# Beans\n## Ingredients\n- beans\n## Instructions\n1. Cook.\n")
    (repo / "broken.md").write_text("# Incomplete source")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Tests",
            "-c",
            "user.email=tests@example.invalid",
            "commit",
            "-qm",
            "Fixture",
        ],
        check=True,
    )
    revision = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    unit = {
        "source": {
            "id": "example",
            "url": "https://github.com/example/recipes",
            "name": "Example",
            "revision": revision,
        },
        "paths": ["beans.md", "rice.md", "broken.md"],
    }
    agent = RecipeSourceAgent(tmp_path)
    first = agent.collect([unit], limit=1)
    assert first["completion_status"] == "incomplete"
    assert len(read_jsonl(agent.shard)) == 1
    second = agent.collect([unit])
    assert len(second["processed"]) == 2
    assert len(second["failures"]) == 1
    content = agent.shard.read_bytes()
    agent.collect([unit])
    assert agent.shard.read_bytes() == content
    assert len(read_jsonl(agent.shard)) == 2
    assert all(row["source_revision"] == revision for row in read_jsonl(agent.shard))
    original_parser = parse_content

    def repaired_parser(text, path):
        if path == "broken.md":
            return original_parser(
                "# Recovered\n## Ingredients\n- beans\n## Instructions\n1. Cook.\n", path
            )
        return original_parser(text, path)

    monkeypatch.setattr("recipe_system.recipes.parse_content", repaired_parser)
    recovered = agent.collect([unit], retry_failures=True)
    assert recovered["failures"] == {}
    assert len(read_jsonl(agent.shard)) == 3
    assert [event["event"] for event in recovered["failure_history"]] == ["failure", "resolved"]
    assert recovered["failure_history"][-1]["resolved_at"]


def test_mdx_subsections_and_microdata():
    mdx = '---\ntitle: Soup\ningredients_subsections:\n- title: Soup\n  items: ["200 mL water"]\ninstructions: ["Heat water."]\n---\n'
    assert markdown(mdx, "soup.mdx")[0]["ingredients"] == ["200 mL water"]
    markup = '<article itemscope itemtype="https://schema.org/Recipe"><h1 itemprop="name">Soup</h1><li itemprop="recipeIngredient">200 mL water</li><p itemprop="recipeInstructions">Heat <b>water</b>.</p></article>'
    row = parse_content(markup, "soup.html")[0]
    assert row["title"] == "Soup"
    assert row["ingredients"] == ["200 mL water"]
    assert "Heat" in row["instructions"][0]


def test_dolph_interleaved_and_navigation_rejection():
    from recipe_system.recipes import interleaved_markdown

    text = "# Salad\nMix in a bowl:\n- 200 g tomato\n- 15 mL olive oil\nServe.\n"
    row = interleaved_markdown(text, "salad.md")[0]
    assert row["ingredients"] == ["200 g tomato", "15 mL olive oil"]
    assert row["instructions"] == ["Mix in a bowl:", "Serve."]
    assert parse_content("https://example.com/\n- Home\n- Contact\n", "archive.gz") == []


def test_extend_plan_preserves_ownership_and_adds_only_new(tmp_path, monkeypatch):
    import copy

    import yaml

    from recipe_system.core import atomic_json
    from recipe_system.recipes import RecipeCoordinator

    old = {
        "id": "old",
        "name": "Old",
        "url": "https://example.invalid/old",
        "revision": "abc",
        "status": "enabled",
        "include": ["*.md"],
    }
    new = {
        "id": "new",
        "name": "New",
        "url": "https://example.invalid/new",
        "revision": "def",
        "status": "enabled",
        "include": ["*.md"],
    }
    original = {
        "workers": 1,
        "item_counts": [1],
        "partitions": {"recipe-agent-01": [{"source": old, "paths": ["old.md"]}]},
    }
    atomic_json(tmp_path / "state/recipes/plan.json", original)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/recipe-sources.yaml").write_text(yaml.safe_dump({"sources": [old, new]}))
    monkeypatch.setattr("recipe_system.recipes.checkout", lambda url, path: "abc")
    monkeypatch.setattr(
        "recipe_system.recipes.git",
        lambda path, *args: "old.md\n" if path.name == "old" else "new.md\n",
    )
    coordinator = RecipeCoordinator(tmp_path)
    extended = coordinator.extend_plan(workers=3)
    assert extended["partitions"]["recipe-agent-01"] == original["partitions"]["recipe-agent-01"]
    assert extended["partitions"]["recipe-agent-02"][0]["paths"] == ["new.md"]
    assert coordinator.extend_plan(workers=3) == extended
    changed = copy.deepcopy(old)
    changed["revision"] = "changed"
    (tmp_path / "config/recipe-sources.yaml").write_text(
        yaml.safe_dump({"sources": [changed, new]})
    )
    import pytest

    with pytest.raises(ValueError, match="versioned refresh"):
        coordinator.extend_plan()


def test_microdata_recipe_name_excludes_publisher():
    markup = '<article itemscope itemtype="https://schema.org/Recipe"><div itemprop="publisher" itemscope itemtype="https://schema.org/Organization"><span itemprop="name">Publisher</span></div><h1 itemprop="name">Actual Soup</h1><li itemprop="recipeIngredient">water</li><p itemprop="recipeInstructions">Heat.</p></article>'
    assert parse_content(markup, "soup.html")[0]["title"] == "Actual Soup"


def test_setext_ingredient_list_followed_by_prose():
    from recipe_system.recipes import leading_list_markdown

    text = "Apple dish\n==========\n\n* 2 apples\n* 15 mL water\n\nSimmer until tender.\n\nServe warm.\n\n## Variations\n* sugar\n"
    row = leading_list_markdown(text, "AppleDish.md")[0]
    assert row["title"] == "Apple dish"
    assert row["ingredients"] == ["2 apples", "15 mL water"]
    assert row["instructions"] == ["Simmer until tender.", "Serve warm."]
