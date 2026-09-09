"""Independent, revision-pinned recipe discovery and resumable shard collection."""

from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import fnmatch
import gzip
import html
import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

import yaml

from .core import atomic_json, atomic_text, load_yaml, now, read_jsonl, stable_id, write_jsonl

INDEX_URL = "https://github.com/bbbenji/awesome-recipes"


def git(path, *args, binary=False):
    result = subprocess.run(
        ["git", "-C", str(path), "-c", "core.quotePath=false", *args],
        capture_output=True,
        check=False,
        timeout=180,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return result.stdout if binary else result.stdout.decode("utf-8", errors="replace")


def checkout(url, cache):
    cache = Path(cache)
    if not (cache / ".git").exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", url, str(cache)],
            capture_output=True,
            check=False,
            timeout=180,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return git(cache, "rev-parse", "HEAD").strip()


def minutes(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        return value
    value = str(value)
    if re.fullmatch(r"PT(?:\d+H)?(?:\d+M)?(?:\d+S)?", value):
        return sum(
            float(n) * {"H": 60, "M": 1, "S": 1 / 60}[u]
            for n, u in re.findall(r"(\d+)([HMS])", value)
        )
    if re.fullmatch(r"\s*\d+(?:\.\d+)?\s*(?:min(?:ute)?s?|minutes)\s*", value, re.IGNORECASE):
        return float(re.search(r"\d+(?:\.\d+)?", value).group())
    return None


def strings(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [
            html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
            for line in value.splitlines()
            if line.strip()
        ]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    if isinstance(value, dict):
        if "text" in value:
            return strings(value["text"])
        if "itemListElement" in value:
            return strings(value["itemListElement"])
        if "originalText" in value:
            return strings(value["originalText"])
        if value.get("note"):
            return strings(value["note"])
    return []


def recipe_objects(obj):
    """Yield actual structured recipes, never arbitrary application JSON."""
    if isinstance(obj, list):
        for item in obj:
            yield from recipe_objects(item)
    elif isinstance(obj, dict):
        if (obj.get("name") or obj.get("title")) and any(
            k in obj for k in ("recipeIngredient", "ingredients", "what")
        ):
            yield obj
        else:
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    yield from recipe_objects(value)


def structured(obj):
    ingredients = strings(obj.get("recipeIngredient", obj.get("ingredients")))
    if not ingredients and obj.get("ingredients_subsections"):
        ingredients = [
            item
            for section in obj["ingredients_subsections"]
            for item in strings(section.get("items"))
        ]
    if obj.get("what"):

        def flatten(mapping):
            for key, value in mapping.items():
                if isinstance(value, dict):
                    yield from flatten(value)
                else:
                    yield f"{value} {key}"

        ingredients = list(flatten(obj["what"]))
    return {
        "title": str(obj.get("name", obj.get("title", ""))),
        "ingredients": ingredients,
        "instructions": strings(
            obj.get(
                "recipeInstructions", obj.get("instructions", obj.get("directions", obj.get("how")))
            )
        ),
        "cuisine": obj.get("recipeCuisine", obj.get("cuisine")),
        "tags": strings(obj.get("keywords", obj.get("tags", obj.get("recipeCategory")))),
        "servings": obj.get("recipeYield", obj.get("servings")),
        "timing": {
            "active_minutes": minutes(obj.get("activeTime")),
            "total_minutes": minutes(obj.get("totalTime", obj.get("readyTime"))),
        },
        "nutrition": obj.get("nutrition"),
        "equipment": strings(obj.get("equipment")),
        "original_url": obj.get("url"),
    }


def markdown(text, path):
    data = {}
    if text.startswith("---"):
        pieces = text.split("---", 2)
        if len(pieces) == 3:
            loaded = yaml.safe_load(pieces[1])
            if isinstance(loaded, dict):
                data = loaded
                text = pieces[2]
    if data.get("ingredients") or data.get("what") or data.get("ingredients_subsections"):
        return [structured(data)]
    title_match = re.search(r"^#\s+(.+)", text, re.MULTILINE)
    title = (
        title_match.group(1).strip()
        if title_match
        else Path(path).stem.replace("-", " ").replace("_", " ")
    )
    title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
    ingredients, instructions, calculations = [], [], []
    mode = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        label = re.sub(r"[#*|:_]", "", line).strip().lower()
        heading = line.startswith("#") or (len(label) < 60 and not re.match(r"^[-*+]\s", line))
        if heading and re.match(
            r"^(?:ingredients?|you will need|what you.ll need|必备原料和工具|原料|材料|食材)\b",
            label,
        ):
            mode = "ingredients"
            continue
        if label == "计算":
            mode = "calculations"
            continue
        if heading and re.match(
            r"^(?:instructions?|directions?|method|preparation|procedure|steps?|操作|做法|步骤)\b",
            label,
        ):
            mode = "instructions"
            continue
        if line.startswith("#"):
            if any(x in label for x in ["notes", "附加", "nutrition", "reference", "credit"]):
                mode = None
            continue
        if re.fullmatch(r"[| :\-]+", line) or line.startswith("!["):
            continue
        bullet = re.match(r"^[-*+]\s+(.+)", line)
        numbered = re.match(r"^\d+[.)]\s+(.+)", line)
        value = re.sub(r"^[-*+]\s+|^\d+[.)]\s+", "", line).strip("| ").strip()
        if mode == "ingredients":
            ingredients.append(value)
        elif mode == "calculations" and bullet:
            calculations.append(value)
        elif mode == "instructions":
            instructions.append(value)
        elif numbered:
            mode = "instructions"
            instructions.append(value)
        elif bullet and not instructions:
            ingredients.append(value)
    # HowToCook explicitly separates unquantified requirements from quantities.
    if calculations:
        ingredients = calculations + [
            x for x in ingredients if not any(x in y for y in calculations)
        ]
    return [
        {
            "title": title,
            "ingredients": ingredients,
            "instructions": instructions,
            "cuisine": None,
            "tags": [],
            "servings": None,
            "timing": {"active_minutes": None, "total_minutes": None},
            "nutrition": None,
            "equipment": [],
        }
    ]


def interleaved_markdown(text, path):
    """Dolph recipes explicitly interleave action paragraphs and ingredient lists."""
    record = markdown(text, path)[0]
    ingredients, instructions = [], []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "![", ">", "<!--", "---")):
            continue
        bullet = re.match(r"^[-*+]\s+(.+)", line)
        if bullet:
            ingredients.append(bullet.group(1))
        elif not re.match(r"^\[.*\]\(.*\)$", line):
            instructions.append(line)
    record.update(ingredients=ingredients, instructions=instructions)
    return [record]


def leading_list_markdown(text, path):
    """Food-recipes uses a Setext title, ingredient bullets, then cooking prose."""
    record = markdown(text, path)[0]
    title = re.search(r"^([^\n]+)\n=+\s*$", text, re.MULTILINE)
    if title:
        record["title"] = title.group(1).strip()
    ingredients, instructions = [], []
    started, cooking = False, False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if cooking and line.startswith("#"):
            break  # Subsequent variations/notes are not the primary method.
        bullet = re.match(r"^[-*+]\s+(.+)", line)
        if bullet and not cooking:
            ingredients.append(bullet.group(1))
            started = True
        elif started:
            if line.startswith(("Forked from", "Source:", "Contributed by")):
                break
            cooking = True
            instructions.append(re.sub(r"^\d+[.)]\s*", "", line))
    record.update(ingredients=ingredients, instructions=instructions)
    return [record]


class MicrodataRecipe(HTMLParser):
    """Parse explicit schema.org microdata; no layout/class-name guesswork."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.fields = {}
        self.title = None
        self.canonical = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")
        frame = {"tag": tag, "attrs": attrs, "text": []}
        self.stack.append(frame)
        if tag in ["meta", "link", "img", "br", "hr", "input", "source", "wbr"]:
            self.handle_endtag(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1]["tag"] == tag:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]["text"].append(data)

    def handle_endtag(self, tag):
        positions = [i for i, frame in enumerate(self.stack) if frame["tag"] == tag]
        if not positions:
            return
        while len(self.stack) > positions[-1]:
            frame = self.stack.pop()
            text = " ".join(" ".join(frame["text"]).split())
            attrs = frame["attrs"]
            prop = attrs.get("itemprop", "")
            value = attrs.get("content", attrs.get("datetime", text))
            if prop and value:
                for key in prop.split():
                    if key == "name":
                        scopes = [
                            entry["attrs"].get("itemtype", "")
                            for entry in [*self.stack, frame]
                            if entry["attrs"].get("itemtype")
                        ]
                        if not scopes or not scopes[-1].rstrip("/").endswith("Recipe"):
                            continue
                    self.fields.setdefault(key, []).append(value)
            if frame["tag"] == "title":
                self.title = text
            if self.stack:
                self.stack[-1]["text"].append(text)

    def records(self):
        ingredients = self.fields.get("recipeIngredient", self.fields.get("ingredients", []))
        instructions = self.fields.get("recipeInstructions", [])
        if not ingredients or not instructions:
            return []
        return [
            structured(
                {
                    "name": (self.fields.get("name") or [self.title])[0],
                    "recipeIngredient": ingredients,
                    "recipeInstructions": instructions,
                    "recipeYield": next(iter(self.fields.get("recipeYield", [])), None),
                    "totalTime": next(iter(self.fields.get("totalTime", [])), None),
                    "url": self.canonical,
                }
            )
        ]


def scraped_text(text, path):
    """Conservative plain-text archive adapter: reject navigation-only pages."""
    lines = text.splitlines()
    original_url = (
        lines[0].strip() if lines and lines[0].startswith(("http://", "https://")) else None
    )
    start = re.search(r"(?im)^\s*[#*_ ]*(?:recipe )?ingredients\s*[*_:]*\s*$", text)
    if not start:
        return []
    body = text[start.start() :]
    stop = re.search(
        r"(?im)^\s*(?:nutrition(?:al information| facts)?|notes|comments|did you make this recipe\??|you may also like|recipe notes|related recipes|leave a reply|share this|rate this recipe)\s*[:?]*\s*$",
        body,
    )
    if stop:
        body = body[: stop.start()]
    record = markdown(body, path)[0]
    slug = original_url.rstrip("/").rsplit("/", 1)[-1] if original_url else Path(path).stem
    record["title"] = slug.replace("-", " ").replace("_", " ")
    record["title_method"] = "source-url-slug (original page heading unavailable)"
    record["original_url"] = original_url
    return [record]


def parse_content(text, path):
    lower = path.lower()
    if "dolph--recipes" in path:
        return interleaved_markdown(text, path)
    if lower.endswith(".gz"):
        return scraped_text(text, path)
    if lower.endswith(".recipe"):
        return [structured(yaml.safe_load(text))]
    if lower.endswith((".json", ".yaml", ".yml")):
        obj = json.loads(text) if lower.endswith(".json") else yaml.safe_load(text)
        return [structured(r) for r in recipe_objects(obj)]
    if lower.endswith((".html", ".htm")):
        output = []
        for block in re.findall(
            r"<script\b[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>",
            text,
            re.DOTALL | re.IGNORECASE,
        ):
            try:
                output.extend(structured(r) for r in recipe_objects(json.loads(block)))
            except (ValueError, TypeError):
                continue
        if not output:
            parser = MicrodataRecipe()
            parser.feed(text)
            output = parser.records()
        return output
    return markdown(text, path)


class RecipeSourceAgent:
    """One exclusive output shard and checkpoint; writes are atomic and resumable."""

    def __init__(self, root=".", agent="recipe-agent-01"):
        self.root = Path(root)
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", agent):
            raise ValueError("Unsafe agent name")
        self.agent = agent
        self.shard = self.root / "data/recipes/raw" / f"{agent}.jsonl"
        self.state_path = self.root / "state/recipes" / f"{agent}.json"

    def collect(self, units, limit=None, retry_failures=False):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.state_path.with_suffix(".lock").open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Shard already has an active owner") from exc
            return self._collect(units, limit, retry_failures)

    def _collect(self, units, limit=None, retry_failures=False):
        state = (
            json.loads(self.state_path.read_text())
            if self.state_path.exists()
            else {
                "agent": self.agent,
                "started_at": now(),
                "sources": {},
                "processed": {},
                "failures": {},
            }
        )
        if "failure_history" not in state:
            state["failure_history"] = [
                dict(failure, event="previously-recorded-failure")
                for failure in state["failures"].values()
            ]
        if state["agent"] != self.agent:
            raise ValueError("Checkpoint belongs to another shard owner")
        rows = {r["id"]: r for r in read_jsonl(self.shard)}
        attempted = 0
        for unit in units:
            source = unit["source"]
            paths = unit["paths"]
            cache = self.root / ".cache/recipes" / source["id"]
            details = state["sources"].setdefault(
                source["id"],
                {"revision": source.get("revision"), "discovered": [], "discovery_complete": True},
            )
            details["discovered"] = sorted(set(details["discovered"]) | set(paths))
            atomic_json(self.state_path, state)
            try:
                revision = checkout(source["url"], cache)
                if source.get("revision") and source["revision"] != revision:
                    raise ValueError("Pinned source revision changed; use a new collection run")
            except (RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
                for path in paths:
                    key = source["id"] + ":" + path
                    if key not in state["processed"]:
                        state["failures"][key] = {
                            "source": source["url"],
                            "item_identifier": path,
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                            "timestamp": now(),
                            "retry_count": state["failures"].get(key, {}).get("retry_count", -1)
                            + 1,
                            "retryable": not isinstance(exc, ValueError),
                        }
                for path in paths:
                    key = source["id"] + ":" + path
                    if key not in state["processed"]:
                        state["failure_history"].append(
                            dict(state["failures"][key], event="failure")
                        )
                atomic_json(self.state_path, state)
                continue
            for path in paths:
                key = source["id"] + ":" + path
                if key in state["processed"] or (key in state["failures"] and not retry_failures):
                    continue
                if limit is not None and attempted >= limit:
                    state["completion_status"] = "incomplete"
                    atomic_json(self.state_path, state)
                    return state
                attempted += 1
                timestamp = now()
                try:
                    payload = git(cache, "show", f"{revision}:{path}", binary=True)
                    if path.endswith(".gz"):
                        payload = gzip.decompress(payload)
                    text = payload.decode("utf-8", errors="replace")
                    if source["id"] == "dolph--recipes":
                        parsed = interleaved_markdown(text, path)
                    elif source["id"] == "obfuscurity--food-recipes":
                        parsed = leading_list_markdown(text, path)
                    else:
                        parsed = parse_content(text, path)
                    if not parsed:
                        raise ValueError(
                            "No supported Recipe structure; original file preserved in pinned Git cache"
                        )
                    ids = []
                    staged = {}
                    for position, record in enumerate(parsed):
                        if not record.get("ingredients") or not record.get("instructions"):
                            raise ValueError(
                                "Missing ingredient or instruction section; source retained for adapter improvement"
                            )
                        original_url = record.pop("original_url", None)
                        rid = stable_id(source["id"], path, str(position))
                        raw = dict(
                            record,
                            id=rid,
                            source_recipe_id=f"{path}#{position}",
                            source_url=source["url"] + "/blob/" + revision + "/" + quote(path),
                            source=source["url"],
                            source_path=path,
                            source_license=source.get(
                                "recipe_license", source.get("license", "unknown")
                            ),
                            attribution=source["name"],
                            retrieved_at=timestamp,
                            source_revision=revision,
                            raw_text=text,
                        )
                        raw["original_source_url"] = original_url
                        raw["publication_allowed"] = source.get("publication_allowed", False)
                        staged[rid] = raw
                        ids.append(rid)
                    rows.update({key: value for key, value in staged.items() if key not in rows})
                    # Persist data before checkpoint so a crash can never mark missing data as done.
                    write_jsonl(self.shard, sorted(rows.values(), key=lambda r: r["id"]))
                    state["processed"][key] = ids
                    previous_failure = state["failures"].pop(key, None)
                    if previous_failure:
                        state["failure_history"].append(
                            dict(previous_failure, event="resolved", resolved_at=now())
                        )
                except (
                    RuntimeError,
                    ValueError,
                    yaml.YAMLError,
                    OSError,
                    subprocess.TimeoutExpired,
                ) as exc:
                    previous = state["failures"].get(key, {})
                    state["failures"][key] = {
                        "source": source["url"],
                        "item_identifier": path,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "timestamp": timestamp,
                        "retry_count": previous.get("retry_count", -1) + 1,
                        "retryable": not isinstance(exc, ValueError),
                    }
                    state["failure_history"].append(dict(state["failures"][key], event="failure"))
                state["updated_at"] = now()
                state["current_cursor"] = key
                atomic_json(self.state_path, state)
        state["completion_status"] = "complete-with-failures" if state["failures"] else "complete"
        state["completed_at"] = now()
        atomic_json(self.state_path, state)
        print(
            json.dumps(
                {
                    "timestamp": now(),
                    "agent": self.agent,
                    "action": "collect",
                    "status": state["completion_status"],
                    "processed": len(state["processed"]),
                    "failures": len(state["failures"]),
                }
            )
        )
        return state


class RecipeCoordinator:
    def __init__(self, root="."):
        self.root = Path(root)

    def discover(self):
        """Read every current index source and inspect complete pinned Git trees."""
        cache = self.root / ".cache/recipes/index"
        checkout(INDEX_URL, cache)
        git(cache, "fetch", "--depth", "1", "origin", "HEAD")
        revision = git(cache, "rev-parse", "FETCH_HEAD").strip()
        index = git(cache, "show", f"{revision}:README.md")
        sources = []
        for name, url in re.findall(
            r"^- \[([^\]]+)\]\((https://(?:github|gist.github).com/[^)]+)\)", index, re.MULTILINE
        ):
            key = url.split("github.com/")[-1].replace("/", "--")
            source = {"id": key, "name": name, "url": url}
            try:
                repo = self.root / ".cache/recipes" / key
                source["revision"] = checkout(url, repo)
                source["files"] = git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
                source["file_count"] = len(source["files"])
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                source.update(status="blocked", reason=str(exc))
            sources.append(source)
        atomic_json(
            self.root / "state/recipes/discovery.json",
            {
                "index_url": INDEX_URL,
                "index_revision": revision,
                "retrieved_at": now(),
                "sources": sources,
            },
        )
        config_path = self.root / "config/recipe-sources.yaml"
        config = load_yaml(config_path) if config_path.exists() else {"sources": []}
        known = {source["id"]: source for source in config["sources"]}
        for source in sources:
            if source["id"] not in known:
                config["sources"].append(
                    {
                        "id": source["id"],
                        "url": source["url"],
                        "name": source["name"],
                        "revision": source.get("revision"),
                        "license": "unknown",
                        "recipe_license": "unknown",
                        "publication_allowed": False,
                        "status": source.get("status", "unsupported"),
                        "reason": source.get(
                            "reason",
                            "New index entry: full tree inspected; corpus paths and recipe licensing require explicit review before enabling.",
                        ),
                        "inspected_file_count": source.get("file_count"),
                    }
                )
        config.update(index_url=INDEX_URL, index_revision=revision, discovered_at=now())
        atomic_text(config_path, yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
        return sources

    def prepare(self):
        """Coordinator-only bulk cache fill before shard workers, avoiding shared Git locks."""
        plan = json.loads((self.root / "state/recipes/plan.json").read_text())
        paths_by_source = {}
        for units in plan["partitions"].values():
            for unit in units:
                paths_by_source.setdefault(unit["source"]["id"], set()).update(unit["paths"])
        for source, paths in sorted(paths_by_source.items()):
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.root / ".cache/recipes" / source),
                    "sparse-checkout",
                    "set",
                    "--no-cone",
                    "--stdin",
                ],
                input="\n".join("/" + path for path in sorted(paths)),
                text=True,
                capture_output=True,
                timeout=180,
                check=True,
            )

    def plan(self, workers=4):
        if workers < 1 or workers > 8:
            raise ValueError("Use 1–8 workers")
        config = load_yaml(self.root / "config/recipe-sources.yaml")
        bins = [[] for _ in range(workers)]
        sizes = [0] * workers
        units = []
        for source in config["sources"]:
            if source["status"] != "enabled":
                continue
            repo = self.root / ".cache/recipes" / source["id"]
            checkout(source["url"], repo)
            files = git(repo, "ls-tree", "-r", "--name-only", source["revision"]).splitlines()
            paths = [
                p
                for p in files
                if any(fnmatch.fnmatch(p, pattern) for pattern in source["include"])
                and not any(fnmatch.fnmatch(p, pattern) for pattern in source.get("exclude", []))
            ]
            for start in range(0, len(paths), 200):
                units.append({"source": source, "paths": paths[start : start + 200]})
        for unit in sorted(
            units, key=lambda u: (-len(u["paths"]), u["source"]["id"], u["paths"][0])
        ):
            i = min(range(workers), key=lambda n: (sizes[n], n))
            bins[i].append(unit)
            sizes[i] += len(unit["paths"])
        plan_path = self.root / "state/recipes/plan.json"
        if plan_path.exists() and list((self.root / "state/recipes").glob("recipe-agent-*.json")):
            previous = json.loads(plan_path.read_text())
            ownership = lambda units: {
                (u["source"]["id"], path) for u in units for path in u["paths"]
            }
            if previous["workers"] != workers or any(
                ownership(previous["partitions"].get(f"recipe-agent-{i + 1:02}", []))
                != ownership(units)
                for i, units in enumerate(bins)
            ):
                raise ValueError(
                    "Existing checkpoint ownership is immutable. Use a new run root to repartition."
                )
        atomic_json(
            self.root / "state/recipes/plan.json",
            {
                "workers": workers,
                "partitions": {f"recipe-agent-{i + 1:02}": units for i, units in enumerate(bins)},
                "item_counts": sizes,
            },
        )
        return bins

    def extend_plan(self, workers=3):
        """Add new source candidates without changing any existing shard ownership."""
        if workers < 1 or workers > 8:
            raise ValueError("Use 1–8 workers")
        plan_path = self.root / "state/recipes/plan.json"
        if not plan_path.exists():
            self.plan(workers)
            return json.loads(plan_path.read_text())
        plan = json.loads(plan_path.read_text())
        owned, revisions = set(), {}
        for units in plan["partitions"].values():
            for unit in units:
                source = unit["source"]
                revisions[source["id"]] = source["revision"]
                owned.update((source["id"], path) for path in unit["paths"])
        additions = []
        for source in load_yaml(self.root / "config/recipe-sources.yaml")["sources"]:
            if source["status"] != "enabled":
                continue
            if source["id"] in revisions and revisions[source["id"]] != source["revision"]:
                raise ValueError(
                    "Existing source revision changed; explicit versioned refresh required"
                )
            repo = self.root / ".cache/recipes" / source["id"]
            checkout(source["url"], repo)
            paths = [
                path
                for path in git(
                    repo, "ls-tree", "-r", "--name-only", source["revision"]
                ).splitlines()
                if (source["id"], path) not in owned
                and any(fnmatch.fnmatch(path, pattern) for pattern in source["include"])
                and not any(fnmatch.fnmatch(path, pattern) for pattern in source.get("exclude", []))
            ]
            for start in range(0, len(paths), 200):
                additions.append({"source": source, "paths": paths[start : start + 200]})
        bins, sizes = [[] for _ in range(workers)], [0] * workers
        for unit in sorted(
            additions, key=lambda u: (-len(u["paths"]), u["source"]["id"], u["paths"][0])
        ):
            index = min(range(workers), key=lambda i: (sizes[i], i))
            bins[index].append(unit)
            sizes[index] += len(unit["paths"])
        next_agent = max(int(name.rsplit("-", 1)[-1]) for name in plan["partitions"]) + 1
        for units, size in zip(bins, sizes, strict=True):
            if units:
                plan["partitions"][f"recipe-agent-{next_agent:02}"] = units
                plan["item_counts"].append(size)
                next_agent += 1
        plan["workers"] = len(plan["partitions"])
        if additions:
            atomic_json(plan_path, plan)
        return plan

    def collect(self, workers=4, retry_failures=False):
        plan_path = self.root / "state/recipes/plan.json"
        if plan_path.exists():
            saved = json.loads(plan_path.read_text())
            bins = list(saved["partitions"].values())
            workers = saved["workers"]
        else:
            bins = self.plan(workers)
        self.prepare()
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, 8)) as pool:
            futures = [
                pool.submit(
                    RecipeSourceAgent(self.root, f"recipe-agent-{i + 1:02}").collect,
                    units,
                    retry_failures=retry_failures,
                )
                for i, units in enumerate(bins)
            ]
            for future in futures:
                future.result()
        return self.manifest()

    def manifest(self):
        config = load_yaml(self.root / "config/recipe-sources.yaml")
        states = [
            json.loads(path.read_text())
            for path in sorted((self.root / "state/recipes").glob("recipe-agent-*.json"))
        ]
        discovered, processed, failures = set(), set(), {}
        completed_sources = []
        for state in states:
            for key, source in state["sources"].items():
                discovered.update(key + ":" + p for p in source["discovered"])
            processed.update(state["processed"])
            failures.update(state["failures"])
        for source in config["sources"]:
            prefix = source["id"] + ":"
            own = {k for k in discovered if k.startswith(prefix)}
            if (
                source["status"] == "enabled"
                and own
                and own <= processed | set(failures)
                and len(own) == source.get("estimated_items")
            ):
                completed_sources.append(source["id"])
        enabled = [s for s in config["sources"] if s["status"] == "enabled"]
        all_done = len(completed_sources) == len(enabled)
        records_written = sum(
            len(read_jsonl(p))
            for p in (self.root / "data/recipes/raw").glob("recipe-agent-*.jsonl")
        )
        per_source = []
        for source in config["sources"]:
            prefix = source["id"] + ":"
            per_source.append(
                {
                    "id": source["id"],
                    "status": source["status"],
                    "reason": source["reason"],
                    "candidate_files_discovered": sum(k.startswith(prefix) for k in discovered),
                    "candidate_files_processed": sum(k.startswith(prefix) for k in processed),
                    "candidate_files_failed": sum(k.startswith(prefix) for k in failures),
                    "index_entries_discovered": source.get("discovered_index_items"),
                    "collection_complete": source["id"] in completed_sources,
                }
            )
        result = {
            "sources": per_source,
            "sources_discovered": len(config["sources"]),
            "sources_enabled": len(enabled),
            "sources_completed": len(completed_sources),
            "completed_source_ids": completed_sources,
            "candidate_files_discovered": len(discovered),
            "candidate_files_processed": len(processed),
            "candidate_files_failed": len(failures),
            "recipes_discovered": records_written if not failures else None,
            "recipes_successfully_processed": records_written,
            "recipes_failed": None if failures else 0,
            "records_written": sum(
                len(read_jsonl(p))
                for p in (self.root / "data/recipes/raw").glob("recipe-agent-*.jsonl")
            ),
            "start_timestamp": min((s["started_at"] for s in states), default=None),
            "completion_timestamp": now() if all_done else None,
            "completion_status": ("complete-with-failures" if failures else "complete")
            if all_done
            else "incomplete",
            "item_accounting": "Recipe candidate files; a structured file can contain multiple records.",
            "blocked_sources": [s["id"] for s in config["sources"] if s["status"] == "blocked"],
            "unsupported_sources": [
                s["id"] for s in config["sources"] if s["status"] == "unsupported"
            ],
            "failures": list(failures.values()),
        }
        atomic_json(self.root / "state/recipes/manifest.json", result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["discover", "plan", "extend-plan", "prepare", "collect", "shard", "manifest"],
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--agent", default="recipe-agent-01")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-failures", action="store_true")
    args = parser.parse_args()
    coordinator = RecipeCoordinator(args.root)
    if args.action == "shard":
        plan = json.loads((Path(args.root) / "state/recipes/plan.json").read_text())
        RecipeSourceAgent(args.root, args.agent).collect(
            plan["partitions"][args.agent], args.limit, args.retry_failures
        )
    elif args.action == "collect":
        coordinator.collect(args.workers, args.retry_failures)
    elif args.action == "plan":
        coordinator.plan(args.workers)
    elif args.action == "extend-plan":
        coordinator.extend_plan(args.workers)
    else:
        getattr(coordinator, args.action)()


if __name__ == "__main__":
    main()
