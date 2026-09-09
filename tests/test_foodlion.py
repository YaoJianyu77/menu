import json
import tempfile
import unittest
from pathlib import Path

from recipe_system.core import atomic_json, read_jsonl, write_jsonl
from recipe_system.foodlion import (
    AccessBlocked,
    FoodLionCoordinator,
    normalize_foodlion,
    product_record,
)


class Client:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        value = self.pages[url]
        if isinstance(value, Exception):
            raise value
        return value


class FoodLionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir()
        (self.root / "config/foodlion.yaml").write_text(
            "location: {city: Williamsburg, state: Virginia, country: United States, timezone: America/New_York}\nstore: null\nlocator_url: https://stores.example/\ncatalog_url: https://catalog.example/\n"
        )
        self.store = {
            "store_id": "fixture-store",
            "name": "Fixture only",
            "address": "Fixture only",
        }

    def test_unknown_product_facts_and_normalization(self):
        (self.root / "config/ingredient-aliases.yaml").write_text(
            "ingredients:\n  tomato:\n    aliases: [roma tomatoes]\n"
        )
        row = product_record(
            {"name": "Roma Tomatoes"},
            "https://example.test/tomato",
            self.store,
            "2026-09-08T12:00:00-04:00",
            "2026-09-08",
        )
        self.assertIsNone(row["price"])
        self.assertIsNone(row["availability"])
        self.assertIsNone(row["product_id"])
        write_jsonl(self.root / "data/foodlion/raw/fl-agent-01.jsonl", [row])
        normalize_foodlion(self.root)
        ingredient = read_jsonl(self.root / "data/foodlion/ingredients.jsonl")[0]
        self.assertEqual(ingredient["canonical_ingredient"], "tomato")
        self.assertIsNone(ingredient["currently_available"])
        self.assertEqual(ingredient["evidence"][0]["store_id"], "fixture-store")

    def test_partition_balanced_and_unique(self):
        partitions = FoodLionCoordinator.partition([{"url": str(i)} for i in range(11)], 4)
        self.assertEqual(len(partitions), 4)
        self.assertEqual(sum(map(len, partitions.values())), 11)
        self.assertEqual(FoodLionCoordinator.partition([]), {})

    def test_blocked_manifest_and_immutable_rerun(self):
        client = Client(
            {"https://stores.example/": "", "https://catalog.example/": AccessBlocked("403 robots")}
        )
        collector = FoodLionCoordinator(self.root, client)
        result = collector.collect("2026-09-08")
        self.assertEqual(result["completion_status"], "blocked")
        self.assertFalse(result["discovery_complete"])
        self.assertIsNone(result["configured_store"])
        self.assertEqual(len(result["failures"]), 2)
        calls = len(client.calls)
        self.assertEqual(collector.collect("2026-09-08"), result)
        self.assertEqual(len(client.calls), calls)

    def test_resume_partition_and_explicit_failures(self):
        good, bad = "https://example.test/good", "https://example.test/bad"
        client = Client(
            {
                good: '<script type="application/ld+json">'
                + json.dumps(
                    {
                        "@type": "Product",
                        "name": "Tomato",
                        "sku": "fixture",
                        "offers": {"availability": "https://schema.org/InStock"},
                    }
                )
                + "</script>",
                bad: AccessBlocked("403"),
            }
        )
        coordinator = FoodLionCoordinator(self.root, client)
        categories = [
            {
                "url": "https://example.test/produce",
                "store_id": "fixture-store",
                "product_urls": [good, bad],
                "discovery_complete": True,
            }
        ]
        state = coordinator.collect_partition("fl-agent-01", categories, self.store, "2026-09-08")
        self.assertTrue(state["complete"])
        self.assertEqual(len(state["processed"]), 1)
        self.assertEqual(len(state["failures"]), 1)
        first = (self.root / "snapshots/foodlion/2026-09-08/raw/fl-agent-01.jsonl").read_bytes()
        coordinator.collect_partition("fl-agent-01", categories, self.store, "2026-09-08")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(
            (self.root / "snapshots/foodlion/2026-09-08/raw/fl-agent-01.jsonl").read_bytes(), first
        )

    def test_persisted_store_not_silently_switched(self):
        previous = {
            "status": "resolved",
            "store": self.store,
            "retrieved_at": "2026-09-08T12:00:00-04:00",
        }
        atomic_json(self.root / "state/foodlion/store.json", previous)
        self.assertEqual(FoodLionCoordinator(self.root, Client({})).resolve_store(), previous)

    def test_supplied_catalog_parallel_snapshot_and_immutable_resume(self):
        config = self.root / "config/foodlion.yaml"
        config.write_text(
            config.read_text().replace(
                "store: null",
                "store: {store_id: fixture-store, name: Fixture only, address: Fixture only}\nconcurrency: 2",
            )
        )
        (self.root / "config/ingredient-aliases.yaml").write_text(
            "ingredients:\n  tomato:\n    aliases: [roma tomatoes]\n"
        )
        urls = [
            "https://example.test/tomato",
            "https://example.test/egg",
            "https://example.test/failure",
        ]
        pages = {
            url: '<script type="application/ld+json">'
            + json.dumps(
                {
                    "@type": "Product",
                    "name": name,
                    "sku": name,
                    "offers": {"price": "2.99", "availability": "https://schema.org/InStock"},
                }
            )
            + "</script>"
            for url, name in zip(urls, ["Roma Tomatoes", "Egg", "Failure"], strict=True)
        }
        pages[urls[2]] = AccessBlocked("fixture blocked product")
        client = Client(pages)
        coordinator = FoodLionCoordinator(self.root, client)
        supplied = {
            "store_id": "fixture-store",
            "discovery_complete": True,
            "categories": [
                {
                    "url": "https://example.test/produce",
                    "product_urls": [urls[0]],
                    "discovery_complete": True,
                },
                {
                    "url": "https://example.test/dairy",
                    "product_urls": urls[1:],
                    "discovery_complete": True,
                },
            ],
        }
        atomic_json(self.root / "catalog.json", supplied)
        result = coordinator.collect("2026-09-08", catalog_manifest_path="catalog.json")
        self.assertEqual(result["completion_status"], "complete-with-failures")
        self.assertEqual(result["products_discovered"], 3)
        self.assertEqual(result["products_processed"], 2)
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(len(result["partitions"]), 2)
        self.assertTrue(result["finalized"])
        ingredients = read_jsonl(self.root / "snapshots/foodlion/2026-09-08/ingredients.jsonl")
        self.assertEqual(len(ingredients), 2)
        self.assertTrue(
            all(
                row["store_id"] == "fixture-store" and row["snapshot_id"] == "2026-09-08"
                for row in ingredients
            )
        )
        self.assertTrue(all(row["currently_available"] for row in ingredients))
        calls = list(client.calls)
        self.assertEqual(
            coordinator.collect("2026-09-08", catalog_manifest_path="catalog.json"), result
        )
        self.assertEqual(client.calls, calls)

    def test_incomplete_supplied_catalog_remains_resumable(self):
        config = self.root / "config/foodlion.yaml"
        config.write_text(
            config.read_text().replace(
                "store: null",
                "store: {store_id: fixture-store, name: Fixture only, address: Fixture only}",
            )
        )
        (self.root / "config/ingredient-aliases.yaml").write_text("ingredients: {}")
        url = "https://example.test/tomato"
        client = Client(
            {url: '<script type="application/ld+json">{"@type":"Product","name":"tomato"}</script>'}
        )
        coordinator = FoodLionCoordinator(self.root, client)
        supplied = {
            "store_id": "fixture-store",
            "discovery_complete": False,
            "categories": [
                {
                    "url": "https://example.test/produce",
                    "product_urls": [url],
                    "discovery_complete": False,
                }
            ],
        }
        atomic_json(self.root / "catalog.json", supplied)
        result = coordinator.collect("2026-09-08", catalog_manifest_path="catalog.json")
        self.assertEqual(result["completion_status"], "incomplete")
        self.assertFalse(result["finalized"])
        coordinator.collect("2026-09-08", catalog_manifest_path="catalog.json")
        self.assertEqual(client.calls, [url])
        supplied["store_id"] = "other-store"
        atomic_json(self.root / "catalog.json", supplied)
        with self.assertRaises(ValueError):
            coordinator.collect("2026-09-08", catalog_manifest_path="catalog.json")

    def test_interrupted_catalog_resumes_only_pending_products(self):
        config = self.root / "config/foodlion.yaml"
        config.write_text(
            config.read_text().replace(
                "store: null",
                "store: {store_id: fixture-store, name: Fixture only, address: Fixture only}",
            )
        )
        (self.root / "config/ingredient-aliases.yaml").write_text("ingredients: {}")
        first, second = "https://example.test/a", "https://example.test/b"

        class InterruptedClient(Client):
            interrupted = False

            def get(self, url):
                if url == second and not self.interrupted:
                    self.interrupted = True
                    raise KeyboardInterrupt("fixture interruption")
                return super().get(url)

        client = InterruptedClient(
            {
                url: '<script type="application/ld+json">'
                + json.dumps({"@type": "Product", "name": url, "sku": url})
                + "</script>"
                for url in [first, second]
            }
        )
        coordinator = FoodLionCoordinator(self.root, client)
        supplied = {
            "store_id": "fixture-store",
            "discovery_complete": True,
            "categories": [
                {
                    "url": "https://example.test/category",
                    "product_urls": [first, second],
                    "discovery_complete": True,
                }
            ],
        }
        atomic_json(self.root / "catalog.json", supplied)
        with self.assertRaises(KeyboardInterrupt):
            coordinator.collect("2026-09-08", catalog_manifest_path="catalog.json")
        result = coordinator.collect("2026-09-08", catalog_manifest_path="catalog.json")
        self.assertEqual(result["completion_status"], "complete")
        self.assertEqual(result["products_processed"], 2)
        self.assertEqual(client.calls, [first, second])
