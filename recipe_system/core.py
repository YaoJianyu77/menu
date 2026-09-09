"""Durable interchange, explicit schemas, and crash-safe checkpoints."""

import hashlib
import json
import os
from datetime import datetime
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml


def now():
    return datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")


def stable_id(*parts):
    return hashlib.sha256(
        json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:24]


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def load_yaml(path):
    with Path(path).open(encoding="utf-8") as stream:
        return yaml.safe_load(stream) or {}


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()
    ]


def write_jsonl(path, rows):
    atomic_text(
        path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    )


def merge_shards(paths, destination):
    rows = {}
    for path in sorted(map(Path, paths)):
        for row in read_jsonl(path):
            key = row["id"]
            if key in rows and rows[key] != row:
                raise ValueError(f"Conflicting immutable records for {key}: {path}")
            rows[key] = row
    write_jsonl(destination, [rows[key] for key in sorted(rows)])
    return list(rows.values())


class Checkpoint:
    """One owner per file. Persist successes after durable shard writes."""

    def __init__(self, path, owner):
        self.path = Path(path)
        self.data = (
            json.loads(self.path.read_text())
            if self.path.exists()
            else {
                "owner": owner,
                "discovered": [],
                "processed": [],
                "failures": {},
                "cursor": None,
                "discovery_complete": False,
                "started_at": now(),
            }
        )
        if self.data["owner"] != owner:
            raise ValueError("Checkpoint belongs to another agent")

    def save(self):
        self.data["updated_at"] = now()
        accounted = set(self.data["processed"]) | set(self.data["failures"])
        self.data["complete"] = (
            self.data["discovery_complete"] and set(self.data["discovered"]) == accounted
        )
        atomic_json(self.path, self.data)

    def pending(self, retry=False):
        done = set(self.data["processed"])
        if not retry:
            done.update(self.data["failures"])
        return sorted(set(self.data["discovered"]) - done)


@cache
def _validator(kind):
    import jsonschema

    schema_path = Path(__file__).parent.parent / "schemas" / f"{kind}.json"
    schema = json.loads(schema_path.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def validate_record(row, kind):
    _validator(kind).validate(row)


def log(agent, source, action, status, **counts):
    print(
        json.dumps(
            dict(
                timestamp=now(), agent=agent, source=source, action=action, status=status, **counts
            )
        )
    )
