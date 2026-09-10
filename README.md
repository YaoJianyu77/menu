# Everyday recipes

A local, private, static recipe library with independent, resumable collection pipelines. No backend, live rendering requests, paid services, deployment, or remote Git pushes are required.

The homepage contains all **2,556 recipes** in a dense, searchable directory. Titles open local cooking pages; the adjacent ↗ opens the original recipe directly. Search ingredients, combine filters, or hide unwanted recipes in your browser. See the [catalog report](docs/catalog-report.md).

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

`site/dist/` and `site/content/` are generated and ignored by Git. Rebuild it from committed source datasets. The private site has no authentication because it is served on your own loopback interface; do not expose the server publicly. No analytics, remote fonts, cookies, or secret configuration are needed. Recipe images are optional and require persisted image-specific permission; the current catalog has no eligible photographs.

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
- `recipe_system/publish.py`: explicit publication allowlist and cooking detail pages.
- `recipe_system/catalog.py`: complete unique catalog, reusable cards, taxonomy, static pagination and local search index.
- `recipe_system/recipe_images.py`: explicit persisted image rights and attribution checks.
- `recipe_system/catalog_validation.py`: reachability, category membership, stable links and rendering checks.
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

The practical matcher uses `config/preferences.yaml` and deterministic classification in `recipe_system/practical.py`. It never asks an LLM to choose meals.

| Component | Maximum | Method |
| --- | ---: | --- |
| Food Lion compatibility | 35 | Required canonical ingredients count once; catalog evidence or an explicit pantry assumption earns full compatibility credit. Unmapped ingredients earn 0.35 uncertainty credit. Optional ingredients have only 5% weight. |
| Convenience | 25 | Active effort 65%, total time 35%; explicit times use configured bands. Missing active time uses Easy/Moderate/Involved credits of 0.8/0.65/0.45. Both times absent receive at most 0.75 credit, without failing the recipe. |
| Meal balance | 25 | Protein 45%, vegetables 35%, staple 15%, protein-plus-vegetables 5%. This is ingredient structure, not calorie or macro estimation. |
| Simplicity/cleanup | 15 | Ingredient count 40%, preparation operations 35%, cleanup 20%, multiple servings 5%. Common cookware is supported. |

Catalog coverage shown on the site is compatible **required** ingredients divided by required ingredients. Optional garnishes do not lower that coverage. Yes and Probably remain distinguishable at ingredient level, with their basis preserved. Exact Richmond Road inventory never affects approval or score. Unknown does not mean unavailable. A substantial unmapped main ingredient (at least 100 g) reduces the compatibility component by 30%; this flags a potentially difficult shopping choice without rejecting the recipe or inventing a substitution.

Time bands give full total-time credit through 30 minutes and 90% through 45 minutes. Low active effort still ranks well with longer unattended cooking. Preparation operations, dough rolling/filling, breading, extra vessels, and English/Chinese action cues determine rough effort—not invented active minutes. Explicit instruction durations can provide a lower bound used for scoring while source times remain unchanged. Overnight preparation reduces convenience. Missing equipment, difficulty, or nutrition fields create no exclusion.

Processed-food dependence and prominent cream/butter/sugar ingredients reduce the meal-balance proxy. Explicit large cooking-fat quantities trigger a modest reduction, adjusted for servings when known; this is not a claim about consumed fat or nutrients. Bread and ordinary cheese are not inherently penalized.

Dish classification distinguishes full meals, mains, sandwiches, pasta, rice/grains, soups/stews, protein salads, breakfast, sides, snacks, desserts, condiments and baking. Dessert ingredient signatures work even when titles are unhelpful. Everyday browsing prioritizes meaningful protein-containing meals; main dishes may need a side. Non-meals are capped below 60 and remain available under All recipes. Genuinely corrupted recipe text is separately capped at 39; absent metadata is not corruption.

Scores mean **90+ Excellent, 80–89 Strong, 70–79 Good, 60–69 Usable, below 60 Low priority**. Everyday meals scoring at least 60 are recommended, and lower-scoring everyday meals remain browsable. Exact duplicate identities remain intact; the discovery view shows the highest-scoring version of each title, with similar versions accessible. All 2,556 unique identities are evaluated; all 2,589 source records retain stored results and provenance.

Changing preferences requires only `make match publish build validate`. Collection and normalization are independent. The previous [collection report](docs/collection-report.md) is a historical engineering report, not the current recommendation policy.

## Publication and licensing

The awesome-recipes index license does not license linked recipe text. Source license inspection and publication permission are separate fields. Unknown third-party content inside MIT/GPL software fixtures remains unknown. Full expressive instructions are published only when the source grant has been affirmatively assessed for this use. Other pages publish structured ingredient facts and attribution and link back for instructions; raw source prose is not copied to the site. Full raw records are local research data, not a publicly licensed redistribution bundle. Review source permissions before any future publication.

The static site exposes full-catalog title/cuisine/meal-type/ingredient/protein/method search, compatibility/time/category filters and individual recipe pages. It builds from published JSON; rendering never calls grocery or recipe sources. Collection diagnostics stay in developer reports; the website focuses on meals, ingredients, effort and compatibility.

## Validation

```sh
make check
.venv/bin/python -m recipe_system.cli validate
```

Tests cover schema rejection, aliases, quantities/fractions/ranges, metric instruction rendering, Food Lion normalization, unavailable/unknown stock, provenance timestamps, stable fingerprints, deterministic scores and coverage, checkpoint ownership/resume, immutable snapshots, idempotent merges, Unicode JSONL, source-prose restrictions, static pages, escaping and all filter controls. Validation checks persisted schemas, raw provenance, source ownership, checkpoint-to-shard consistency, manifests, real product references, repeated score output and published measurement constraints.

The final collection report records what was collected, which adapters still failed, and which external sources blocked access. It is not a claim of complete national Food Lion inventory or exhaustive recovery from every indexed source.

Optional web formatting and real-browser verification (development tools only):

```sh
npx --yes prettier@3.6.2 --check site/hidden.js site/catalog.js site/style.css tests/browser/catalog.cjs
npm install --prefix .cache/browser --no-save --package-lock=false playwright@1.63.0
.cache/browser/node_modules/.bin/playwright install chromium
PLAYWRIGHT_MODULE="$PWD/.cache/browser/node_modules/playwright" node tests/browser/catalog.cjs
```

The browser smoke test starts its own local server and checks full-catalog search, combined filters, sorting, pagination, recipe pages, stateful back navigation, local annotations and mobile layout. It creates annotations only in its temporary browser profile.

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

## Complete catalog website

```sh
make publish build validate      # uses persisted data; does not collect or normalize
make serve                      # http://127.0.0.1:8000
.venv/bin/python -m recipe_system.catalog_validation
PLAYWRIGHT_MODULE="$PWD/.cache/browser/node_modules/playwright" node tests/browser/catalog.cjs
```

The website consists of one dense catalog and 2,556 local detail pages. There are no category or recommendation routes. Stable recipe paths retain the previous `recipes/<stable-id>.html` format; titles link locally, and a separate muted ↗ links directly to the persisted original source. Valid HTTP(S) source URLs open with `target="_blank" rel="noopener noreferrer"`. Missing source URLs omit only the icon; the local page remains available. No URLs are guessed or fetched during builds.

The three/two/one-column directory retains 120 rows per JavaScript page, five filters, Default/Name/Time sorting and sticky controls. Search evaluates the full non-hidden dataset before pagination. Query parameters retain controls and pagination; sessionStorage preserves the last catalog query for the detail-page Back to recipes link. Without JavaScript every title remains available on the homepage.

Ingredient search is generated from the existing canonical vocabulary and `config/ingredient-aliases.yaml`, original ingredient text, original/display titles and filter metadata. Text uses Unicode normalization and case folding. Longest known ingredient phrases are grouped, so “green onion” and “chicken breast” work as ingredients. Multiple query parts use AND matching. Under Default sorting, exact titles come first, then strong title matches, all-ingredient matches, other ingredient matches, and incidental metadata matches; ties preserve the existing order. Name and Time remain explicit manual sorts. Search does not alter the ranking pipeline or expose scores.

Detail pages display metric ingredients, permitted normalized instructions, and a clear original-source link. Instruction redistribution remains permission-gated: 533 recipes provide local instructions; 2,023 provide ingredients and the source link. Only explicitly permitted persisted images can appear on detail pages; no images appear in the directory. Raw/provenance data, personal annotations and ranking remain intact. The internal `site/content/recipes.json` interchange is not deployed. Build replaces the output directory and emits 2,557 HTML pages plus static assets and the ingredient search index.

## Browser-local hidden recipes

Rows provide an accessible × action. Hidden stable IDs use the existing localStorage key `my-recipes:hidden:v1`; this preference survives refreshes in the same browser/origin, without device synchronization or Git changes. Undo lasts ten seconds (longer while hovered or focused). Hidden management allows Restore and Restore all. Hidden recipes are excluded from search, filters, counts and pagination; Clear resets only filters. Corrupt storage and unknown IDs are safe. No backend, cookies or login are required.

The browser suite verifies local cooking pages and separate external icons using intercepted source responses, without scraping original sites. It also covers all filters, URL state, dense layouts, keyboard controls, hiding, Undo, restoration, malformed storage and the JavaScript-disabled complete directory. Old multi-page collection/publication reports remain historical.

## GitHub Pages

Repository: https://github.com/YaoJianyu77/menu

Site: https://yaojianyu77.github.io/menu/

`.github/workflows/pages.yml` tests and builds the persisted catalog on pushes to `master`, then publishes `site/dist` using GitHub's official Pages artifact and deployment actions. It does not collect, normalize, or rerank data. Repository Settings → Pages → Source must be **GitHub Actions**. The complete `main` history has been merged into `master`; ongoing deployments use `master`, the repository default and permitted Pages deployment branch.

All site assets, navigation, pagination, recipe URLs and the search index use relative URLs, so the same artifact works under `/menu/` without a localhost or domain-specific build setting. No credentials or personal browser notes enter the artifact. Browser checks accept a production URL:

```sh
BASE_URL=https://yaojianyu77.github.io/menu/ \
BROWSER_REPORT=/tmp/menu-live-browser.json \
PLAYWRIGHT_MODULE="$PWD/.cache/browser/node_modules/playwright" \
node tests/browser/catalog.cjs
```

The public site exposes published recipe content only. Developer data stays out of the Pages artifact; the GitHub repository itself is public. Browser notes remain local to each browser/origin and are not synchronized.
