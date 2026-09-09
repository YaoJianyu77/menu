"""Store-scoped Food Lion snapshots, with fail-closed access and explicit gaps."""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .core import Checkpoint, atomic_json, load_yaml, now, read_jsonl, stable_id, write_jsonl


class AccessBlocked(RuntimeError):
    pass


class RespectfulClient:
    """Check robots before each origin; cache successful responses within a run."""

    def __init__(self, interval=1.0, user_agent="PersonalRecipeResearch/1.0"):
        self.interval = interval
        self.user_agent = user_agent
        self.robots = {}
        self.cache = {}
        self.last_request = 0.0

    def _request(self, url):
        time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        self.last_request = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            if error.code in (401, 403, 429):
                raise AccessBlocked(f"HTTP {error.code} at {url}; no bypass attempted") from error
            raise

    def get(self, url):
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
        if not parser.can_fetch(self.user_agent, url):
            raise AccessBlocked(f"robots.txt disallows {url}")
        delay = parser.crawl_delay(self.user_agent) or 0
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
    availability = offers.get("availability", "")
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
        "price": offers.get("price"),
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
                except (OSError, ValueError, AccessBlocked) as error:
                    failures.append(failure("foodlion-locator", url, error))
        except (OSError, ValueError, AccessBlocked) as error:
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
        if (directory / "manifest.json").exists():
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
                            stack.extend(item.get("@graph", []))
                            if item.get("@type") == "Product":
                                products.append(item)
                if len(products) != 1 or not products[0].get("name"):
                    raise ValueError("Expected exactly one named Product in public JSON-LD")
                record = product_record(products[0], url, store, now(), snapshot_id)
                if record["id"] not in rows:
                    rows[record["id"]] = record
                write_jsonl(shard, [rows[key] for key in sorted(rows)])
                checkpoint.data["processed"] = sorted(set(checkpoint.data["processed"]) | {url})
                checkpoint.data["failures"].pop(url, None)
            except (OSError, ValueError, AccessBlocked) as error:
                previous = checkpoint.data["failures"].get(url)
                item = failure("foodlion", url, error)
                item["retry_count"] = previous["retry_count"] + 1 if previous else 0
                checkpoint.data["failures"][url] = item
            checkpoint.save()
        checkpoint.data["cursor"] = None
        checkpoint.save()
        return checkpoint.data

    def collect(self, snapshot_id=None):
        started = now()
        snapshot_id = snapshot_id or started[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-[a-zA-Z0-9_-]+)?", snapshot_id):
            raise ValueError("snapshot ID must begin with local YYYY-MM-DD")
        directory = self.root / "snapshots/foodlion" / snapshot_id
        manifest_path = directory / "manifest.json"
        if manifest_path.exists():
            # Finalized snapshots are immutable, even when blocked. New attempts need a new ID.
            return json.loads(manifest_path.read_text())
        store_state = self.resolve_store()
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
        except (OSError, ValueError, AccessBlocked) as error:
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


def normalize_foodlion(root):
    from .normalize import canonicalize

    root = Path(root)
    aliases = load_yaml(root / "config/ingredient-aliases.yaml")
    latest = root / "state/foodlion/latest.json"
    snapshot_id = json.loads(latest.read_text())["snapshot_id"] if latest.exists() else None
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
    return {"products": len(products), "ingredients": len(ingredients), "snapshot_id": snapshot_id}
