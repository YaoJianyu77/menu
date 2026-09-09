# Everyday recipes

A local, private, static recipe library with independent, resumable collection pipelines. No backend, live rendering requests, paid services, deployment, or remote Git pushes are required.

**Availability is evidence, not a guess.** The configured store remains **1234 Richmond Road, Williamsburg, VA 23185**. Its exact inventory is unverified, but Food Lion's permitted public grocery catalog supplies 22,994 product IDs/URLs and conservative likelihood evidence for 155 canonical ingredients. Other Food Lion stores may supply additional evidence without changing the selected store. See the [collection report](docs/collection-report.md), [Food Lion evidence](docs/foodlion-evidence.md), and [parser recovery audit](docs/parser-recovery.md) for measured coverage and remaining failures.

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
- `recipe_system/evidence.py`: permitted first-party catalog observations and conservative ingredient evidence.
- `recipe_system/recovery.py`, `archives.py`: root-cause audits and generalized failure recovery.
- `recipe_system/quality.py`: source coverage and representative recommendation audits.
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

A candidate file can contain zero, one or multiple recipes. Manifests distinguish file accounting from actual recipe records: when parsing failed files prevents knowing the number of recipes, the recipe count is unknown rather than invented. Every discovered file must be processed or explicitly failed before an enabled source is accounted for. `candidate_accounting_complete` means all declared files were attempted. Source `COMPLETE` additionally requires no unresolved extraction failures, pending members or unexplored candidates. `PARTIAL`, `BLOCKED`, `NOT_A_RECIPE_SOURCE` and `UNSUPPORTED` remain distinct; the overall collection is currently `PARTIAL`. Blocked/unsupported sources stay listed separately from enabled-source completion.

Food Lion snapshot dates and all collector timestamps use `America/New_York` with ISO 8601 UTC offsets. Store resolution records the official locator source and address. A locator entity identifier is not assumed to be an ecommerce catalog ID. The chosen store never silently changes. Finalized snapshots, including blocked ones, remain immutable; retry with a fresh date/suffix. `state/foodlion/latest.json` selects the current snapshot for normalization/matching. Previous snapshots remain intact.

Food Lion's store inventory interface returned HTTP 403. Its separate, robots-permitted `/groceries/` public catalog was collected through advertised sitemaps and an all-aisles listing. This is national catalog evidence, not local inventory. Product detail/category coverage is not exhaustive. The original blocked snapshot remains unchanged; catalog observations are separate under `data/foodlion/evidence/`. See the [evidence capability and collection commands](docs/foodlion-evidence.md).

Collectors respect robots (including applicable AI-agent policies), authentication, CAPTCHA, rate limits and access restrictions. A restriction is a recorded blocker, never a reason to rotate identities or bypass protection. The BBC archive's remote bodies were not fetched because its robots rules disallow this use.

## Schemas and provenance

Raw recipe records include a stable internal ID, original title/ingredients/instructions/timing/nutrition, source repository and path, source recipe ID, original site URL when supplied, attribution, source license, retrieval timestamp, commit and original source text. They are never edited to enforce measurement preferences. Normalized recipes retain `raw_id`, immutable source URL, license, revision and normalized ingredient records with original text, original quantity/unit, metric quantity/unit and canonical name.

Product records preserve explicit product IDs, names, brands, sizes, price/availability, store and source metadata. Unknown fields remain null. Canonical ingredient rows include actual product record IDs and per-product evidence, snapshot ID, store ID and last verification timestamp. Matching requires that evidence to claim availability. Unverified or unparsed ingredient names never imply stock.

Personal annotations are separate from source records. Recipe pages support favorite, cooked, rating, notes, modifications, last-cooked date and would-cook-again fields in browser localStorage. Export JSON regularly. To persist exported notes in Git, copy them to `data/personal/recipes.json` and run `make publish build`. Import/export is local, with no server writes.

## Normalization and deduplication

Ingredient aliases are explicit in `config/ingredient-aliases.yaml`; there is no LLM in the production pipeline. Unknown names remain unresolved. Preparation suffix removal is deliberately limited. Different chicken cuts remain separate. Substitutions are a separate evidence field and no substitutions are silently inferred.

Measurements use deterministic kitchen conventions: small volume measures are 5/15 mL; a US cup is 240 mL. US fluid ounces, pints/quarts/gallons and mass ounces/pounds have explicit conversion constants. Fractions, ranges, decimal quantities and Fahrenheit temperatures are converted. No ingredient volume becomes a mass without density evidence. Counts remain counts with a null measurement unit and an explicit container/count unit where available. Package counts and per-package sizes stay separate; drained mass is never inferred. Original measurements live only in raw/source-preservation fields. Ambiguous ounce-labelled vessel capacities are marked for source checking rather than converted to an unsupported weight. Unquantified measures are labelled by metric measure size instead of guessing a quantity. Explicit French, German, Greek and Chinese small-volume forms are supported; unrecognized wording remains flagged for source verification.

Active time remains null unless the source explicitly supplies active time; prep time is not silently substituted. A source total time within the active-time budget can support an upper bound without filling in active time. Contradictory instruction durations and long advance preparation are flagged, not repaired with invented times. Total time is normalized only from explicit supported timing. Nutrition is preserved when explicit, never invented. Cooking method and ingredient group signals are reproducible text/alias heuristics, not dietary assessments.

Deduplication fingerprints exact normalized title, cuisine, quantities, ingredient identities, optional flags and instruction text. Ingredient order does not affect the fingerprint. Exact duplicates are grouped with a stable representative ID; records and meaningful variants are retained. Package sizes and count units participate in fingerprints. Duplicate representatives appear by default; variants remain browsable. Grouping intentionally misses ambiguous near-duplicates instead of destroying variants.

## Deterministic ranking

Defaults live in `config/preferences.yaml` and `config/meal-rules.yaml`. Nominal weights are Food Lion 40, time 25, meal balance 20, simplicity 15.

Food Lion states are **Verified**, **Likely available**, **Unknown**, and **Unavailable** only with affirmative absence evidence. Verified requires configured-store evidence; another store or national catalog supports likelihood. Missing catalog entries are unknown. Every observed match cites real Food Lion product IDs, source URLs, store specificity and observation time. Catalog coverage is `(verified + likely) / ingredient count`; verified-store coverage is separate. Confidence is `(verified + 0.6 × likely) / count`, an evidence indicator, not a stock probability.

The availability component averages essential (85%) and optional (15%) groups, falling back to the essential group when no optional ingredients exist. Within each group verified earns 1, likely 0.85, explicitly unavailable 0. Let `c` be weighted credit per ingredient and `o` the weighted fraction with observed evidence. Unknown contributes neither credit nor observed weight. Displayed Food Lion score is `40 × c / o`, or null when nothing is observed. The overall base score is:

```text
100 × (time + meal_balance + simplicity + 40 × c) / (60 + 40 × o)
```

Thus an inventory access block removes unobserved availability weight instead of assigning zero availability. A wholly unknown catalog does not artificially depress the score, but cannot support approval. All ingredient counts and the assessed denominator are persisted and displayed.

Time uses 70% active and 30% total credit, each `min(1, preferred_limit / explicit_minutes)`. Missing times earn zero. Explicit total time no greater than 15 minutes supports the active-time upper bound; active minutes still remain null. Meal balance uses protein presence 40%, vegetable presence 35%, both 25%, normalized across enabled signals. These are ingredient-presence proxies, **not** measured nutrition or evidence of sufficient portions. Configured processed-food and rich-ingredient fractions reduce this proxy. Simplicity uses ingredient count 45%, instruction count 35%, method/common/reusable ingredient evidence 20%; thresholds and bonuses are configurable. Normal cookware receives no equipment penalty.

Transparent adjustments then apply: non-meal roles multiply by 0.35; missing protein/vegetable structure by 0.8; unresolved ingredient identity by `1 − 0.5 × unresolved_fraction`; extraction/timing quality issues by 0.25. Unresolved identity is a parsing limitation, separate from missing stock evidence. Dish roles use explicit tags/title patterns; desserts, drinks, dips, sauces and components remain collected but are excluded from meal recommendations. Adjustments and evidence appear in every stored result.

Strict approval requires configured verified coverage, every essential ingredient verified, supported active-time budget and score at least 65. Provisional recommendations require score at least 65, explicit total time at most 40 minutes, protein and vegetable signals, catalog evidence coverage at least 50%, at most 20 ingredients, at most 50% unresolved ingredient identities, and no exclusion/quality restriction. They are labelled **recommended with caveats**, requiring a check of active time and exact-store availability. Zero current recipes have verified-store approval. Duplicates do not flood recommendations. All results—including rejected and unassessed records—remain stored. Matching has no clock, randomness, or free-form LLM judgment.

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

The browser smoke test checks distinct catalog and verified-store coverage, duplicate visibility, recipe pages, local annotations and mobile layout against the generated dataset. It creates annotations only in its temporary browser profile.

## Data quality workflows

```sh
.venv/bin/python -m recipe_system.recovery audit
.venv/bin/python -m recipe_system.recovery retry --agent recipe-agent-03
.venv/bin/python -m recipe_system.quality all
.venv/bin/python -m recipe_system.recipes manifest
.venv/bin/python -m recipe_system.evidence rebuild .
make pipeline
```

Recovery retries only affected failed items accepted by the improved parser. `state/recipes/recovery/baseline.jsonl` freezes the original 934 failures; outcomes and per-shard improvement reports retain original errors and later resolution. New-source exclusions and archive member outcomes are separate. Source completeness is measured from pinned trees and actual checkpoints, not inferred from a zero pending-worker count. Quality audits preserve past manual review passes; new cohort rows require renewed review when inputs change.
