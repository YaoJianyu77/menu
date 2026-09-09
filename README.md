# Everyday recipes

A local, private, static recipe library with independent, resumable collection pipelines. No backend, live rendering requests, paid services, deployment, or remote Git pushes are required.

**Availability is evidence, not a guess.** The initial Food Lion run is blocked by catalog access restrictions. The selected store is **1234 Richmond Road, Williamsburg, VA 23185**, but its catalog store ID remains unverified. The site therefore shows unverified ingredient availability and does not approve recipes on invented inventory. See [collection report](docs/collection-report.md) for actual counts and remaining source failures.

## Quick start

Python 3.11+ (3.12 used here), Git, and Node for the JavaScript syntax check. Runtime dependencies are PyYAML and jsonschema. The website itself has no third-party runtime dependencies.

```sh
make setup                     # uv creates .venv and installs pinned development tools
make pipeline                  # offline normalize → deduplicate → match → publish → build → validate
make serve                     # http://127.0.0.1:8000 (loopback only)
make test
make lint
make format
```

Without uv, create a Python virtual environment with `python3 -m venv .venv`, then run `.venv/bin/pip install -r requirements-dev.txt`. Python must have its standard venv/ensurepip support installed.

`site/dist/` is generated and ignored by Git. Rebuild it from committed source datasets. The private site has no authentication because it is served on your own loopback interface; do not expose the server publicly. No analytics, remote fonts, remote images, cookies, or secret configuration are needed.

## Architecture and durable files

```text
Food Lion collection → raw product snapshots → products → canonical ingredients
Recipe source discovery → independent raw shards → normalized recipes → duplicate groups
Canonical ingredients + normalized recipes + preferences → every match result
Match results + normalized recipes + personal annotations → site/content → site/dist
```

- `config/`: store, all discovered source decisions, explicit ingredient aliases, scoring preferences.
- `recipe_system/core.py`: JSONL interchange, atomic writes, stable IDs, checkpoints, schemas.
- `recipe_system/foodlion.py`: respectful access client, store resolution, product shards and snapshots.
- `recipe_system/recipes.py`: `RecipeCoordinator`, source enumeration, `RecipeSourceAgent`, format adapters.
- `recipe_system/normalize.py`: measurement/ingredient normalization and conservative duplicate grouping.
- `recipe_system/match.py`: deterministic scoring; all evaluated records retained.
- `recipe_system/publish.py`: explicit publication allowlist and static HTML generation.
- `data/foodlion/`: current derived product and ingredient views.
- `data/recipes/raw/`: immutable successful source records in agent-owned JSONL shards.
- `data/recipes/normalized/recipes.jsonl`: centrally regenerated recipes with raw provenance.
- `data/recipes/duplicates/`: fingerprints and non-destructive grouping decisions.
- `data/matches/results.jsonl`: approved, rejected and needs-review records.
- `data/personal/recipes.json`: optional personal annotations keyed by stable recipe ID.
- `snapshots/foodlion/<local-date>/`: historical manifest, raw shards, products and ingredients.
- `state/`: discovered items, source pins, ownership plans, progress, failures and manifests.
- `.cache/recipes/`: ignored Git repositories containing pinned source revisions and failed source bodies.
- `schemas/`: machine-readable JSON Schemas; `tests/`: synthetic fixtures and regressions.
- `agents/`: ownership and collector-specific operating instructions.

Changing preferences only needs `make match publish build`. Changing presentation only needs `make build` (or `make publish build` when the published data model changes). A new inventory snapshot does not recollect recipes. All transformations after collection work offline.

## Collection commands and resuming

```sh
make discover-recipes
make plan-recipes
make extend-recipes            # after enabling new sources; preserves existing ownership
make collect-recipes
make resume
.venv/bin/python -m recipe_system.recipes shard --agent recipe-agent-02
.venv/bin/python -m recipe_system.recipes shard --agent recipe-agent-02 --retry-failures
.venv/bin/python -m recipe_system.recipes manifest
make collect-foodlion
.venv/bin/python -m recipe_system.cli collect-foodlion --snapshot-id 2026-09-09-retry01
```

The recipe coordinator reads the full awesome-recipes index, records its commit, inspects linked Git trees and preserves every source decision. It centrally prefetches corpus blobs before parallel readers start, avoiding shared Git-object download contention. Complete candidate paths are enumerated from pinned Git trees, split into bounded units and balanced across three workers in the initial run. Large sources cross shards; each path has exactly one owner. Thread workers support repeatable CLI collection, and the initial collection also used three independent coordinating agents.

New index links are persisted as `unsupported` pending an explicit source format/license decision. Review `config/recipe-sources.yaml`, set declared `include`/`exclude` patterns and license evidence, then generate a plan. Do not reinterpret a tool category as proof that no recipe corpus exists: this run inspected fixtures in recipe tools too. Sources may be enabled, disabled by source type, blocked, unsupported, or not a recipe source. Preference filtering never occurs during collection.

Completed items are skipped. Failed items are retried only when requested; reasons and retry counts remain in state. Success data is durable before the checkpoint marks completion. Atomic replacement prevents partial JSONL or checkpoint visibility. A resumed collection keeps the saved partition plan rather than changing owners when worker count changes. Do not manually run the same agent/shard twice concurrently. To add sources, enable them in configuration and run `make extend-recipes collect-recipes`: only new candidate paths receive fresh shard IDs. Existing partitions stay unchanged. Source revision changes require an explicit versioned refresh; the current planner rejects changes to existing pins rather than silently replacing raw records.

Raw records retain source content, so normalization does not need the cache. The cache also retains the original content of failed candidate files; keep it when working on parser improvements. Git source pins and failure paths permit refetching if the original repository remains accessible. Refreshing sources is an explicit operation; ordinary resume never silently upgrades source commits.

## Completion and snapshots

A candidate file can contain zero, one or multiple recipes. Manifests distinguish file accounting from actual recipe records: when parsing failed files prevents knowing the number of recipes, the recipe count is unknown rather than invented. Every discovered file must be processed or explicitly failed before an enabled source is accounted for. `complete-with-failures` means all declared candidates were attempted; it does **not** mean all recipe bodies were recovered. Blocked/unsupported sources stay listed separately from enabled-source completion.

Food Lion snapshot dates and all collector timestamps use `America/New_York` with ISO 8601 UTC offsets. Store resolution records the official locator source and address. A locator entity identifier is not assumed to be an ecommerce catalog ID. The chosen store never silently changes. Finalized snapshots, including blocked ones, remain immutable; retry with a fresh date/suffix. `state/foodlion/latest.json` selects the current snapshot for normalization/matching. Previous snapshots remain intact.

Food Lion's live catalog rejected this environment. No verified automated category/page enumerator could be established. The tested generic public JSON-LD product adapter and category partitioning primitives cannot turn national/global offers into store inventory. See [Food Lion collector documentation](agents/foodlion/README.md) for the supported manifest-based orchestration and its evidence requirements. Removing the HTTP block alone does not establish a complete live catalog adapter.

Collectors respect robots (including applicable AI-agent policies), authentication, CAPTCHA, rate limits and access restrictions. A restriction is a recorded blocker, never a reason to rotate identities or bypass protection. The BBC archive's remote bodies were not fetched because its robots rules disallow this use.

## Schemas and provenance

Raw recipe records include a stable internal ID, original title/ingredients/instructions/timing/nutrition, source repository and path, source recipe ID, original site URL when supplied, attribution, source license, retrieval timestamp, commit and original source text. They are never edited to enforce measurement preferences. Normalized recipes retain `raw_id`, immutable source URL, license, revision and normalized ingredient records with original text, original quantity/unit, metric quantity/unit and canonical name.

Product records preserve explicit product IDs, names, brands, sizes, price/availability, store and source metadata. Unknown fields remain null. Canonical ingredient rows include actual product record IDs and per-product evidence, snapshot ID, store ID and last verification timestamp. Matching requires that evidence to claim availability. Unverified or unparsed ingredient names never imply stock.

Personal annotations are separate from source records. Recipe pages support favorite, cooked, rating, notes, modifications, last-cooked date and would-cook-again fields in browser localStorage. Export JSON regularly. To persist exported notes in Git, copy them to `data/personal/recipes.json` and run `make publish build`. Import/export is local, with no server writes.

## Normalization and deduplication

Ingredient aliases are explicit in `config/ingredient-aliases.yaml`; there is no LLM in the production pipeline. Unknown names remain unresolved. Preparation suffix removal is deliberately limited. Different chicken cuts remain separate. Substitutions are a separate evidence field and no substitutions are silently inferred.

Measurements use deterministic kitchen conventions: small volume measures are 5/15 mL; a US cup is 240 mL. US fluid ounces, pints/quarts/gallons and mass ounces/pounds have explicit conversion constants. Fractions, ranges, decimal quantities and Fahrenheit temperatures are converted. No ingredient volume becomes a mass without density evidence. Counts remain counts with a null unit. Original measurements live only in raw/source-preservation fields. Unquantified measures are labelled by metric measure size instead of guessing a quantity. Unrecognized international wording is flagged for source verification.

Active time remains null unless the source explicitly supplies active time; prep time is not silently substituted. Total time is normalized only from explicit supported timing. Nutrition is preserved when explicit, never invented. Cooking method and ingredient group signals are reproducible text/alias heuristics, not dietary assessments.

Deduplication fingerprints exact normalized title, cuisine, quantities, ingredient identities, optional flags and instruction text. Ingredient order does not affect the fingerprint. Exact duplicates are grouped with a stable representative ID; records and meaningful variants are retained. Grouping intentionally misses ambiguous near-duplicates instead of destroying variants.

## Deterministic ranking

Defaults are in `config/preferences.yaml`; all four weights total 100:

| Component | Points | Formula |
| --- | ---: | --- |
| Food Lion | 40 | 85% essential coverage + 15% optional coverage. If no optional ingredients, use essential coverage for both. Only verified available ingredients receive credit. |
| Time | 25 | 70% active + 30% total. Each earns `min(1, preferred_limit / actual_minutes)`; unknown evidence earns zero by default. |
| Meal balance | 20 | Protein ingredient presence 40%, vegetable presence 35%, both 25%, normalized across enabled signals. A configured processed-ingredient fraction can reduce credit. |
| Simplicity | 15 | Ingredient count 45%, instruction count 35%, method/common/reusable ingredient evidence 20%. Counts linearly decline from configured simple to complex limits. |

Protein/vegetable presence is an explainable **proxy**. It does not establish sufficient portions, nutrient totals or nutritional adequacy. Simplicity method bonuses honor the selected one-pan, sheet-pan, air-fryer, oven and stovetop preferences, plus explicit low-cleanup/batch evidence. Normal equipment never incurs an equipment penalty. Common/reusable ingredient signals use the explicit canonical vocabulary; they are not inferred product prices or shopping histories.

Approval additionally requires minimum score, configured coverage and missing-ingredient limits, known active time by default, and active time within the limit. Unknown availability cannot receive approval. `needs-review` denotes unresolved inventory without a definitive conflicting restriction; other failures are rejected. Missing (explicit unavailable) and unknown (no verified evidence) remain distinct. Coverage counts each unique canonical ingredient once; if listed as both optional and essential, it is essential. Every result includes component scores, reasons, ingredient evidence and an input fingerprint. There is no clock or randomness in scoring.

## Publication and licensing

The awesome-recipes index license does not license linked recipe text. Source license inspection and publication permission are separate fields. Unknown third-party content inside MIT/GPL software fixtures remains unknown. Full expressive instructions are published only when the source grant has been affirmatively assessed for this use. Other pages publish structured ingredient facts and attribution and link back for instructions; raw source prose is not copied to the site. Full raw records are local research data, not a publicly licensed redistribution bundle. Review source permissions before any future publication.

The static site exposes recipe name/cuisine/status/time/protein/method/coverage filters and individual recipe pages. It builds from published JSON; rendering never calls grocery or recipe sources. It deliberately shows collection limitations and unverified values.

## Validation

```sh
make check
.venv/bin/python -m recipe_system.cli validate
```

Tests cover schema rejection, aliases, quantities/fractions/ranges, metric instruction rendering, Food Lion normalization, unavailable/unknown stock, provenance timestamps, stable fingerprints, deterministic scores and coverage, checkpoint ownership/resume, immutable snapshots, idempotent merges, Unicode JSONL, source-prose restrictions, static pages, escaping and all filter controls. Validation checks persisted schemas, raw provenance, source ownership, checkpoint-to-shard consistency, manifests, real product references, repeated score output and published measurement constraints.

The final collection report records what was collected, which adapters still failed, and which external sources blocked access. It is not a claim of complete national Food Lion inventory or exhaustive recovery from every indexed source.

Optional web formatting and real-browser verification (development tools only):

```sh
npx --yes prettier@3.6.2 --check site/app.js site/style.css tests/browser/smoke.cjs
npm install --prefix .cache/browser --no-save --package-lock=false playwright@1.63.0
.cache/browser/node_modules/.bin/playwright install chromium
make serve  # keep running in another terminal
PLAYWRIGHT_MODULE="$PWD/.cache/browser/node_modules/playwright" node tests/browser/smoke.cjs
```

The browser smoke test uses the initial blocked-inventory dataset to check that a 100% verified-coverage filter returns no recipes. Adjust that fixture-specific expectation after a real verified inventory snapshot is collected. It creates annotations only in its temporary browser profile.
