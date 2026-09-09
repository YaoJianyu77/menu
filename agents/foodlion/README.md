# Food Lion collection

`FoodLionCoordinator` lives in `recipe_system/foodlion.py`. Configuration and persisted store resolution are separate: `config/foodlion.yaml` records the user's explicit choice; `state/foodlion/store.json` records how it was resolved and when. Never equate the locator's Yext entity identifier with the grocery catalog store identifier.

The user selected **1234 Richmond Road, Williamsburg, VA 23185, United States**. The official locator calls this **Food Lion Grocery Store of Williamsburg**. Its public locator identifier is `https://stores.foodlion.com/#5046160`. The catalog store ID remains unknown.

The initial live check found `https://foodlion.com/robots.txt` returning HTTP 403. The respectful client stops at that restriction. It does not fetch protected catalog endpoints, replay browser credentials, or infer inventory from general grocery knowledge. The locator's robots file permits its public pages; Williamsburg lists five physical stores, so a city alone does not uniquely resolve a store.

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
