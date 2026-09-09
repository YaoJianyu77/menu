"""Store-scoped Food Lion snapshots, with fail-closed access and explicit gaps."""

from __future__ import annotations

import html
import json
import re
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from jsonschema import ValidationError

from .core import (
    Checkpoint,
    atomic_json,
    load_yaml,
    merge_shards,
    now,
    read_jsonl,
    stable_id,
    validate_record,
    write_jsonl,
)


class AccessBlocked(RuntimeError):
    pass


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Do not follow a location whose robots/access policy has not been checked."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AccessBlocked(
            f"HTTP {code} redirect from {req.full_url} to {newurl}; target not requested"
        )


class RespectfulClient:
    """Check robots before each origin; cache successful responses within a run."""

    def __init__(self, interval=1.0, user_agent="PersonalRecipeResearch/1.0"):
        self.interval = interval
        self.user_agent = user_agent
        self.robots = {}
        self.cache = {}
        self.last_request = 0.0
        self.opener = urllib.request.build_opener(RefuseRedirects())
        self.lock = threading.Lock()

    def _request(self, url):
        time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        self.last_request = time.monotonic()
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            if error.code in (401, 403, 429):
                raise AccessBlocked(f"HTTP {error.code} at {url}; no bypass attempted") from error
            raise

    def get(self, url):
        # One global rate limiter/cache across the independent collection workers.
        with self.lock:
            return self._get(url)

    def _get(self, url):
        origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
        if origin not in self.robots:
            robots_url = origin + "/robots.txt"
            try:
                body = self._request(robots_url)
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                body = ""
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(body.splitlines())
            self.robots[origin] = parser
        parser = self.robots[origin]
        identities = (self.user_agent, "ChatGPT-User", "GPTBot", "OAI-SearchBot")
        for identity in identities:
            if not parser.can_fetch(identity, url):
                raise AccessBlocked(f"robots.txt disallows {url} for {identity}")
            delay = parser.crawl_delay(identity) or 0
            self.interval = max(self.interval, delay)
        if url not in self.cache:
            self.cache[url] = self._request(url)
        return self.cache[url]


def failure(source, item, error):
    return {
        "source": source,
        "item_identifier": item,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "timestamp": now(),
        "retry_count": 0,
        "retryable": not isinstance(error, AccessBlocked),
    }


def product_record(product, url, store, retrieved_at, snapshot_id):
    """Translate explicit schema.org Product fields; absent availability stays unknown."""
    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if len(offers) == 1 else {}
    if not isinstance(offers, dict):
        raise TypeError("Product offers must be an object or a list of objects")
    availability = offers.get("availability") or ""
    if not isinstance(availability, str):
        raise TypeError("Product availability must be a URL string or null")
    stock = (
        True
        if availability.endswith("/InStock")
        else False
        if availability.endswith("/OutOfStock")
        else None
    )
    brand = product.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    product_id = product.get("sku") or product.get("productID") or product.get("gtin13")
    return {
        "id": stable_id("foodlion", snapshot_id, str(product_id or url)),
        "product_id": product_id,
        "name": product.get("name"),
        "brand": brand,
        "category": product.get("category"),
        "subcategory": None,
        "package_size": product.get("size"),
        "unit": None,
        "price": float(offers["price"]) if offers.get("price") is not None else None,
        "sale_price": None,
        "price_unit": offers.get("priceCurrency"),
        "availability": stock,
        "source_url": url,
        "store_id": store["store_id"],
        "store_name": store.get("name"),
        "store_address": store.get("address"),
        "image_url": product.get("image"),
        "retrieved_at": retrieved_at,
        "source_metadata": {
            "schema_org": product,
            "snapshot_id": snapshot_id,
            "method": "public-jsonld",
        },
    }


class FoodLionCoordinator:
    def __init__(self, root, client=None):
        self.root = Path(root)
        self.config = load_yaml(self.root / "config/foodlion.yaml")
        self.client = client or RespectfulClient(
            self.config.get("request_interval_seconds", 1),
            self.config.get("user_agent", "PersonalRecipeResearch/1.0"),
        )

    def resolve_store(self):
        path = self.root / "state/foodlion/store.json"
        old = json.loads(path.read_text()) if path.exists() else None
        configured = self.config.get("store")
        if configured:
            if not all(configured.get(k) for k in ("name", "address")):
                raise ValueError("Configured store requires verified name and address")
            if old and old.get("store") == configured:
                return old
            result = {
                "status": "resolved" if configured.get("store_id") else "catalog-id-unresolved",
                "store": configured,
                "resolved_by": "explicit configuration",
                "retrieved_at": now(),
                "previous_store": old.get("store") if old else None,
            }
            atomic_json(path, result)
            return result
        if old:
            return old
        locator = self.config["locator_url"]
        candidates, failures = [], []
        try:
            body = self.client.get(locator)
            urls = sorted(
                {
                    urljoin("https://stores.foodlion.com/", value.replace("../", ""))
                    for value in re.findall(r'href="([^"]*williamsburg/[^"#?]*)"', body)
                }
            )
            for url in urls:
                try:
                    page = self.client.get(url)

                    def field(pattern, page=page):
                        match = re.search(pattern, page)
                        return html.unescape(match.group(1)) if match else None

                    street = field(r'itemprop="streetAddress" content="([^"]+)"')
                    postal = field(r'itemprop="postalCode">([^<]+)')
                    name = field(r'itemprop="name" content="([^"]+)"')
                    candidates.append(
                        {
                            "store_id": None,
                            "name": name or "Food Lion",
                            "address": f"{street}, Williamsburg, VA {postal}, United States"
                            if street and postal
                            else street,
                            "source_url": url,
                            "locator_entity_id": field(
                                r'itemtype="https://schema.org/GroceryStore" itemid="([^"]+)"'
                            ),
                        }
                    )
                except (OSError, ValueError, TypeError, ValidationError, AccessBlocked) as error:
                    failures.append(failure("foodlion-locator", url, error))
        except (OSError, ValueError, TypeError, ValidationError, AccessBlocked) as error:
            failures.append(failure("foodlion-locator", locator, error))
        result = {
            "status": "unresolved",
            "store": None,
            "candidates": candidates,
            "resolved_by": "official Williamsburg locator; explicit store selection and verified catalog ID required",
            "retrieved_at": now(),
            "source_url": locator,
            "failures": failures,
        }
        atomic_json(path, result)
        return result

    @staticmethod
    def partition(categories, concurrency=4):
        shards = [[] for _ in range(min(concurrency, len(categories)))]
        for index, category in enumerate(
            sorted(categories, key=lambda value: (-value.get("estimated_size", 1), value["url"]))
        ):
            shards[index % len(shards)].append(category)
        return {f"fl-agent-{i + 1:02d}": shard for i, shard in enumerate(shards)}

    def collect_partition(self, agent, categories, store, snapshot_id, retry=False):
        """Collect independently enumerated store-scoped public product URLs.

        Each category must supply its complete item URLs and discovery_complete evidence.
        This adapter does not assert that a global storefront is a store inventory.
        """
        if not re.fullmatch(r"fl-agent-[0-9]{2}", agent):
            raise ValueError("Invalid shard owner")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-[a-zA-Z0-9_-]+)?", snapshot_id):
            raise ValueError("Invalid snapshot ID")
        if not store.get("store_id"):
            raise ValueError("A verified catalog store ID is required")
        if any(category.get("store_id") != store["store_id"] for category in categories):
            raise ValueError("Category store context mismatch")
        directory = self.root / "snapshots/foodlion" / snapshot_id
        existing_manifest = directory / "manifest.json"
        if existing_manifest.exists() and json.loads(existing_manifest.read_text()).get(
            "finalized", True
        ):
            raise ValueError("Finalized snapshots are immutable")
        checkpoint = Checkpoint(self.root / "state/foodlion" / f"{snapshot_id}-{agent}.json", agent)
        urls = sorted({url for category in categories for url in category.get("product_urls", [])})
        checkpoint.data["discovered"] = sorted(set(checkpoint.data["discovered"]) | set(urls))
        checkpoint.data["discovery_complete"] = bool(categories) and all(
            category.get("discovery_complete") for category in categories
        )
        checkpoint.data["categories"] = categories
        checkpoint.save()
        shard = directory / "raw" / f"{agent}.jsonl"
        rows = {row["id"]: row for row in read_jsonl(shard)}
        for url in checkpoint.pending(retry=retry):
            checkpoint.data["cursor"] = url
            checkpoint.save()
            try:
                body = self.client.get(url)
                products = []
                for block in re.findall(
                    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                    body,
                    re.DOTALL | re.IGNORECASE,
                ):
                    payload = json.loads(block)
                    stack = payload if isinstance(payload, list) else [payload]
                    while stack:
                        item = stack.pop()
                        if isinstance(item, dict):
                            graph = item.get("@graph") or []
                            if not isinstance(graph, list):
                                raise TypeError("JSON-LD @graph must be a list")
                            stack.extend(graph)
                            if item.get("@type") == "Product":
                                products.append(item)
                if len(products) != 1 or not products[0].get("name"):
                    raise ValueError("Expected exactly one named Product in public JSON-LD")
                record = product_record(products[0], url, store, now(), snapshot_id)
                validate_record(record, "product")
                if record["id"] not in rows:
                    rows[record["id"]] = record
                write_jsonl(shard, [rows[key] for key in sorted(rows)])
                checkpoint.data["processed"] = sorted(set(checkpoint.data["processed"]) | {url})
                checkpoint.data["failures"].pop(url, None)
            except (OSError, ValueError, TypeError, ValidationError, AccessBlocked) as error:
                previous = checkpoint.data["failures"].get(url)
                item = failure("foodlion", url, error)
                item["retry_count"] = previous["retry_count"] + 1 if previous else 0
                checkpoint.data["failures"][url] = item
            checkpoint.save()
        checkpoint.data["cursor"] = None
        checkpoint.save()
        return checkpoint.data

    def _collect_manifest(self, snapshot_id, supplied_path, store_state, started):
        """Orchestrate a locally supplied, independently verified public catalog index."""
        path = Path(supplied_path)
        if not path.is_absolute():
            path = self.root / path
        catalog = load_yaml(path)
        store = store_state.get("store") or {}
        if not store.get("store_id") or catalog.get("store_id") != store["store_id"]:
            raise ValueError("Catalog manifest must match the verified configured catalog store ID")
        categories = catalog.get("categories")
        if not isinstance(categories, list):
            raise TypeError("Catalog manifest categories must be a list")
        claimed_urls = set()
        for category in categories:
            if not isinstance(category, dict) or not isinstance(category.get("url"), str):
                raise TypeError("Every category requires a URL")
            if category.get("store_id", store["store_id"]) != store["store_id"]:
                raise ValueError("Category store context mismatch")
            category["store_id"] = store["store_id"]
            urls = category.get("product_urls")
            if not isinstance(urls, list) or any(
                not isinstance(url, str) or urlsplit(url).scheme not in {"http", "https"}
                for url in urls
            ):
                raise ValueError("Every category requires explicit public HTTP(S) product_urls")
            # Product overlaps across categories belong to the first deterministic category.
            category["product_urls"] = sorted(set(urls) - claimed_urls)
            claimed_urls.update(urls)
        categories.sort(key=lambda category: category["url"])
        directory = self.root / "snapshots/foodlion" / snapshot_id
        plan_path = directory / "collection-plan.json"
        partitions = self.partition(categories, max(1, int(self.config.get("concurrency", 4))))
        plan = {"store": store, "catalog": catalog, "partitions": partitions}
        if plan_path.exists():
            if json.loads(plan_path.read_text()) != plan:
                raise ValueError(
                    "Collection plan changed; start a distinct snapshot to preserve shard ownership"
                )
        else:
            atomic_json(plan_path, plan)
        manifest_path = directory / "manifest.json"
        previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        manifest = {
            "snapshot_id": snapshot_id,
            "snapshot_date": started[:10],
            "start_timestamp": previous.get("start_timestamp", started),
            "completion_timestamp": None,
            "configured_location": self.config["location"],
            "configured_store": store,
            "store_resolution": store_state,
            "categories_discovered": categories,
            "categories_completed": [],
            "products_discovered": len(claimed_urls),
            "products_processed": 0,
            "failures": [],
            "warnings": [],
            "collector_version": "2",
            "completion_status": "in-progress",
            "finalized": False,
            "discovery_complete": bool(catalog.get("discovery_complete"))
            and all(category.get("discovery_complete") is True for category in categories),
            "partitions": partitions,
            "catalog_manifest_path": str(path),
            "catalog_manifest_fingerprint": stable_id(catalog),
        }
        atomic_json(manifest_path, manifest)
        atomic_json(self.root / "state/foodlion/latest.json", {"snapshot_id": snapshot_id})
        states = {}
        worker_errors = []
        with ThreadPoolExecutor(max_workers=max(1, len(partitions))) as pool:
            futures = {
                pool.submit(self.collect_partition, agent, assigned, store, snapshot_id): agent
                for agent, assigned in partitions.items()
            }
            for future in as_completed(futures):
                agent = futures[future]
                try:
                    states[agent] = future.result()
                except (OSError, ValueError, TypeError, ValidationError, AccessBlocked) as error:
                    worker_errors.append(failure("foodlion", agent, error))
        paths = [directory / "raw" / f"{agent}.jsonl" for agent in sorted(partitions)]
        try:
            for shard_path in paths:
                for row in read_jsonl(shard_path):
                    validate_record(row, "product")
                    if (
                        row["store_id"] != store["store_id"]
                        or row.get("source_metadata", {}).get("snapshot_id") != snapshot_id
                    ):
                        raise ValueError("Shard product provenance disagrees with collection plan")
            merged = merge_shards(paths, directory / "raw/merged.jsonl")
        except (OSError, ValueError, TypeError, ValidationError) as error:
            manifest["completion_status"] = "incomplete"
            manifest["products_processed"] = len(
                {url for state in states.values() for url in state["processed"]}
            )
            manifest["failures"] = (
                [
                    item
                    for agent in sorted(states)
                    for _, item in sorted(states[agent]["failures"].items())
                ]
                + worker_errors
                + [failure("foodlion", "central-validation-merge", error)]
            )
            atomic_json(manifest_path, manifest)
            return manifest
        processed = {url for state in states.values() for url in state["processed"]}
        failures = [
            item
            for agent in sorted(states)
            for _, item in sorted(states[agent]["failures"].items())
        ]
        failed_urls = {item["item_identifier"] for item in failures}
        manifest["products_processed"] = len(processed)
        manifest["unique_products"] = len(merged)
        manifest["failures"] = failures + sorted(
            worker_errors, key=lambda item: item["item_identifier"]
        )
        manifest["categories_completed"] = [
            category["url"]
            for category in categories
            if category.get("discovery_complete")
            and set(category["product_urls"]) <= processed | failed_urls
        ]
        accounted = claimed_urls == processed | failed_urls
        complete = manifest["discovery_complete"] and accounted and not worker_errors
        manifest["completion_status"] = (
            "complete-with-failures"
            if complete and failures
            else "complete"
            if complete
            else "incomplete"
        )
        manifest["finalized"] = complete
        manifest["completion_timestamp"] = now() if complete else None
        if not manifest["discovery_complete"]:
            manifest["warnings"].append(
                "Supplied catalog index does not establish complete discovery"
            )
        if not accounted:
            manifest["warnings"].append(
                "Unprocessed items remain; resume this unchanged collection plan"
            )
        try:
            normalize_foodlion(self.root, snapshot_id=snapshot_id, write_snapshot=True)
        except (OSError, ValueError, TypeError, ValidationError) as error:
            manifest["completion_status"] = "incomplete"
            manifest["finalized"] = False
            manifest["completion_timestamp"] = None
            manifest["failures"].append(failure("foodlion", "central-normalization", error))
        atomic_json(manifest_path, manifest)
        return manifest

    def collect(self, snapshot_id=None, catalog_manifest_path=None):
        started = now()
        snapshot_id = snapshot_id or started[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-[a-zA-Z0-9_-]+)?", snapshot_id):
            raise ValueError("snapshot ID must begin with local YYYY-MM-DD")
        directory = self.root / "snapshots/foodlion" / snapshot_id
        manifest_path = directory / "manifest.json"
        if manifest_path.exists():
            # Finalized snapshots are immutable, even when blocked. New attempts need a new ID.
            previous = json.loads(manifest_path.read_text())
            if previous.get("finalized", True):
                return previous
        store_state = self.resolve_store()
        supplied_manifest = catalog_manifest_path or self.config.get("catalog_manifest_path")
        if supplied_manifest:
            return self._collect_manifest(snapshot_id, supplied_manifest, store_state, started)
        errors = list(store_state.get("failures", []))
        warnings = []
        catalog = self.config["catalog_url"]
        categories = []
        try:
            body = self.client.get(catalog)
            # A rendered storefront without an enumerable store catalog is not evidence of inventory.
            warnings.append(
                f"Catalog HTML retrieved ({len(body)} characters); no verified store-scoped complete catalog adapter available"
            )
        except (OSError, ValueError, TypeError, ValidationError, AccessBlocked) as error:
            errors.append(failure("foodlion", catalog, error))
        if store_state["status"] != "resolved":
            errors.append(
                failure(
                    "foodlion",
                    "store-context",
                    AccessBlocked(
                        "Store catalog ID unresolved; inventory cannot be attributed to the configured Williamsburg store"
                    ),
                )
            )
        status = "blocked" if errors else "unsupported"
        state = {
            "agent": "fl-agent-01",
            "source": "foodlion",
            "snapshot_id": snapshot_id,
            "discovered": [],
            "processed": [],
            "failed": errors,
            "cursor": None,
            "pagination": {},
            "discovery_complete": False,
            "completion_status": status,
            "updated_at": now(),
        }
        atomic_json(self.root / "state/foodlion" / f"{snapshot_id}-fl-agent-01.json", state)
        manifest = {
            "snapshot_id": snapshot_id,
            "snapshot_date": started[:10],
            "start_timestamp": started,
            "completion_timestamp": now(),
            "configured_location": self.config["location"],
            "configured_store": store_state.get("store"),
            "store_resolution": store_state,
            "categories_discovered": categories,
            "categories_completed": [],
            "products_discovered": 0,
            "products_processed": 0,
            "failures": errors,
            "warnings": warnings,
            "collector_version": "1",
            "completion_status": status,
            "discovery_complete": False,
            "partitions": self.partition(categories),
        }
        write_jsonl(directory / "raw/fl-agent-01.jsonl", [])
        write_jsonl(directory / "products.jsonl", [])
        write_jsonl(directory / "ingredients.jsonl", [])
        atomic_json(manifest_path, manifest)
        atomic_json(self.root / "state/foodlion/latest.json", {"snapshot_id": snapshot_id})
        print(
            json.dumps(
                {
                    "timestamp": now(),
                    "agent": "FoodLionCoordinator",
                    "source": "foodlion",
                    "action": "snapshot",
                    "status": status,
                    "products": 0,
                    "failures": len(errors),
                }
            )
        )
        return manifest


def normalize_foodlion(root, snapshot_id=None, write_snapshot=False):
    from .normalize import canonicalize

    root = Path(root)
    aliases = load_yaml(root / "config/ingredient-aliases.yaml")
    latest = root / "state/foodlion/latest.json"
    snapshot_id = snapshot_id or (
        json.loads(latest.read_text())["snapshot_id"] if latest.exists() else None
    )
    directory = root / "snapshots/foodlion" / snapshot_id if snapshot_id else root / "data/foodlion"
    rows = {}
    for path in sorted((directory / "raw").glob("*.jsonl")):
        for row in read_jsonl(path):
            if row["id"] in rows and rows[row["id"]] != row:
                raise ValueError(f"Conflicting Food Lion raw ID: {row['id']}")
            rows[row["id"]] = row
    products, ingredients = [], {}
    for row in sorted(rows.values(), key=lambda value: value["id"]):
        canonical = canonicalize(row["name"], aliases)
        product = {
            **row,
            "raw_id": row["id"],
            "canonical_ingredient": canonical,
            "snapshot_id": snapshot_id,
        }
        products.append(product)
        # Only explicitly mapped ingredients can substantiate matches.
        entry = ingredients.setdefault(
            canonical,
            {
                "name": canonical,
                "canonical_ingredient": canonical,
                "aliases": [],
                "product_ids": [],
                "product_count": 0,
                "currently_available": None,
                "category": row.get("category"),
                "last_verified_at": row["retrieved_at"],
                "normalization_method": "explicit-alias-or-exact-name",
                "snapshot_id": snapshot_id,
                "store_id": row.get("store_id"),
                "evidence": [],
            },
        )
        entry["product_ids"].append(row["id"])
        entry["product_count"] += 1
        entry["aliases"] = sorted(set(entry["aliases"] + [row["name"]]))
        entry["last_verified_at"] = max(entry["last_verified_at"], row["retrieved_at"])
        entry["evidence"].append(
            {
                "product_id": row["id"],
                "source_product_id": row.get("product_id"),
                "snapshot_id": snapshot_id,
                "store_id": row.get("store_id"),
                "verified_at": row["retrieved_at"],
                "availability": row.get("availability"),
                "source_url": row["source_url"],
            }
        )
    for entry in ingredients.values():
        statuses = [item["availability"] for item in entry["evidence"]]
        entry["currently_available"] = (
            True if True in statuses else False if all(s is False for s in statuses) else None
        )
    write_jsonl(root / "data/foodlion/products.jsonl", products)
    write_jsonl(
        root / "data/foodlion/ingredients.jsonl", [ingredients[key] for key in sorted(ingredients)]
    )
    if write_snapshot:
        manifest_path = directory / "manifest.json"
        if manifest_path.exists() and json.loads(manifest_path.read_text()).get("finalized", True):
            raise ValueError("Finalized snapshot derived files are immutable")
        write_jsonl(directory / "products.jsonl", products)
        write_jsonl(
            directory / "ingredients.jsonl", [ingredients[key] for key in sorted(ingredients)]
        )
    return {"products": len(products), "ingredients": len(ingredients), "snapshot_id": snapshot_id}
