"""Local workflows; every transform operates on durable data without network access."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "discover-recipes",
            "plan-recipes",
            "extend-recipes",
            "collect-recipes",
            "collect-foodlion",
            "normalize",
            "normalize-recipes",
            "normalize-foodlion",
            "deduplicate",
            "match",
            "publish",
            "build",
            "pipeline",
            "validate",
        ],
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--snapshot-id")
    parser.add_argument(
        "--catalog-manifest", help="Verified local store-scoped Food Lion category manifest"
    )
    args = parser.parse_args()
    root = Path(args.root)
    from .foodlion import FoodLionCoordinator, normalize_foodlion
    from .match import match_recipes
    from .normalize import deduplicate, normalize_recipes
    from .publish import build, publish
    from .recipes import RecipeCoordinator
    from .validate import validate

    actions = {
        "discover-recipes": lambda: RecipeCoordinator(root).discover(),
        "plan-recipes": lambda: RecipeCoordinator(root).plan(args.workers),
        "extend-recipes": lambda: RecipeCoordinator(root).extend_plan(args.workers),
        "collect-recipes": lambda: RecipeCoordinator(root).collect(
            args.workers, args.retry_failures
        ),
        "collect-foodlion": lambda: FoodLionCoordinator(root).collect(
            args.snapshot_id, args.catalog_manifest
        ),
        "normalize-foodlion": lambda: normalize_foodlion(root),
        "normalize-recipes": lambda: normalize_recipes(root),
        "normalize": lambda: [normalize_foodlion(root), normalize_recipes(root)],
        "deduplicate": lambda: deduplicate(root),
        "match": lambda: match_recipes(root),
        "publish": lambda: publish(root),
        "build": lambda: build(root),
        "validate": lambda: validate(root),
    }
    if args.command == "pipeline":
        result = {}
        for step in ["normalize", "deduplicate", "match", "publish", "build", "validate"]:
            value = actions[step]()
            result[step] = (
                len(value) if isinstance(value, list) else value if step == "validate" else "ok"
            )
    else:
        result = actions[args.command]()
        if isinstance(result, list):
            result = {"records": len(result)}
        elif args.command == "publish":
            result = {"published": len(result["recipes"])}
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
