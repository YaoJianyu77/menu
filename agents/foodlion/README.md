# Food Lion collection

`FoodLionCoordinator` lives in `recipe_system/foodlion.py`. Configuration and persisted store resolution are separate: `config/foodlion.yaml` records the user's explicit choice; `state/foodlion/store.json` records how it was resolved and when. Never equate the locator's Yext entity identifier with the grocery catalog store identifier.

The user selected **1234 Richmond Road, Williamsburg, VA 23185, United States**. The official locator calls this **Food Lion Grocery Store of Williamsburg**. Its public locator identifier is `https://stores.foodlion.com/#5046160`. The catalog store ID remains unknown.

The preliminary live check found `https://foodlion.com/robots.txt` returning HTTP 403. During the persisted initial snapshot attempt, robots was accessible but `https://foodlion.com/` returned HTTP 403; the snapshot records that exact catalog-page failure. The respectful client stops at that restriction. It does not fetch protected catalog endpoints, replay browser credentials, or infer inventory from general grocery knowledge. The locator's robots file permits its public pages; Williamsburg lists five physical stores, so a city alone does not uniquely resolve a store.

Run `make collect-foodlion` (or `.venv/bin/python -m recipe_system.cli collect-foodlion`). The finalized manifest is immutable, including blocked attempts. To explicitly retry later on the same local date, pass a distinct dated ID through Python:

```python
from pathlib import Path
from recipe_system.foodlion import FoodLionCoordinator
FoodLionCoordinator(Path('.')).collect('2026-09-08-retry-01')
```

The snapshot contains its manifest, raw shards, products, and ingredients. A blocked snapshot has zero products and `discovery_complete: false`, with explicit access and store-resolution errors. Empty inventory never supports a positive availability claim. `normalize_foodlion(root)` rebuilds current normalized inventory from the latest immutable raw snapshot, independently of recipe collection or preferences.

The reusable `collect_partition(agent, categories, store, snapshot_id, retry=False)` adapter processes publicly accessible schema.org Product pages, after robots checks. Each category must supply `url`, verified `store_id`, `product_urls`, and `discovery_complete`. Upstream enumeration must establish actual store scope and complete pagination before asserting discovery completion. No working live full-catalog enumeration adapter was established under the current restriction; the coordinator reports this explicitly when HTML is reachable but no verified enumerator exists.

`partition(categories, concurrency=4)` deterministically assigns discovered categories to unique owners; there are no category agents to launch when discovery itself is blocked. Each owner writes only `snapshots/foodlion/<snapshot>/raw/fl-agent-NN.jsonl` and `state/foodlion/<snapshot>-fl-agent-NN.json`. Atomic shard replacement precedes checkpoint success accounting. Each discovered URL is either successful or an explicit failure. Ordinary resume retains failures; `retry=True` retries only failed/pending URLs. Finalized snapshots reject subsequent shard mutations.

The collector never silently treats partial discovery as a complete snapshot. HTTP 401, 403, 429 and robots denial block access. Successful requests are cached in-process, crawl delay is honored, and requests are spaced at least one second by default. Historical raw snapshots are the persistent cache and are never recollected by a same-ID rerun.

## Verified catalog manifest orchestration

When a complete category/product index has been obtained through permitted normal interfaces, the coordinator can ingest a **local JSON or YAML catalog manifest**. This is an explicit input adapter; direct live Food Lion category discovery remains unverified under the access restriction. A manifest cannot establish permission to fetch restricted URLs, and the client still checks robots, relevant AI-agent policies, rate limits, and redirects for every product origin.

Set the independently verified catalog `store_id` in `config/foodlion.yaml` first. The manifest must contain the same `store_id`, a boolean `discovery_complete`, and `categories`. Each category supplies its `url`, a `product_urls` list, and its own `discovery_complete`. It may preserve pagination/cursor evidence and other source metadata alongside those fields. `discovery_complete: true` is appropriate only after verifying the entire permitted category/page inventory; false is preserved as incomplete. Optional category `store_id` values must also match. Duplicate product URLs across categories are centrally assigned to a single owner.

```python
from pathlib import Path
from recipe_system.foodlion import FoodLionCoordinator

FoodLionCoordinator(Path('.')).collect(
    '2026-09-08-verified-index',
    catalog_manifest_path='data/foodlion/catalog-index.yaml',
)
```

The same path may be configured as `catalog_manifest_path` in `config/foodlion.yaml`. The manifest and configured store become an immutable `collection-plan.json` within the snapshot. A changed plan requires a new snapshot ID so ownership never shifts beneath an existing checkpoint.

The coordinator partitions categories dynamically across up to configured `concurrency` workers. Each worker owns its separate shard/checkpoint. Their HTTP requests share a global respectful rate limiter and cache. A successful shard writes each schema-validated product before recording success. The central coordinator validates store/snapshot provenance, merges shards idempotently, creates snapshot and current normalized inventory, and records explicit product failures. Product URL counts and unique commercial product counts remain separate.

Interrupted snapshots retain `finalized: false`; rerun the exact same command to resume only pending URLs. `complete` and `complete-with-failures` both require full discovery and every discovered URL accounted for. Failures are retained in the manifest; they do not disappear behind the completion status. Partial discovery stays `incomplete` and cannot become complete without a newly verified plan in a distinct snapshot. Finalized snapshots reject writes and same-ID reruns return their unchanged manifest.

Tests cover two concurrent category owners, an explicit blocked product, central normalization with real fixture product provenance, immutable finalized reruns, partial discovery, and interruption after one durable product followed by a resume that requests only the pending product. These tests use clearly labelled synthetic fixtures and do not imply that the current live Food Lion interface has been verified.
