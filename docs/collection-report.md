# Initial collection report

Generated 2026-09-08T23:42:00-04:00. No deployment or remote push performed.

## Outcome

- Index: 42 source links inspected; 20 enabled recipe sources.
- All 3,167 declared candidate files accounted for: 2,233 processed, 934 explicit failures.
- Successful raw recipe records: 2,235. Two additional records come from multi-recipe candidate files.
- Normalized recipes and persisted match results: 2,235 each.
- Exact duplicate records grouped without deletion: 16.
- Static build: 2,236 pages; no live data dependency.
- Recommendation statuses: {'needs-review': 2235}.
- Explicit active cooking time: 0 records; explicit total time: 304 records. Unknown timing was not estimated.

`complete-with-failures` is candidate accounting, not complete recipe recovery. Parsing failures prevent knowing the total number of actual recipes in failed files. Global recipe-discovered/failed counts therefore remain null. All rejected and unverified recipes remain stored.

## Food Lion

The user-selected location is Food Lion Grocery Store of Williamsburg, 1234 Richmond Road, Williamsburg, VA 23185. Official locator evidence and retrieval time are in `state/foodlion/store.json`. The locator entity identifier is preserved separately; it was not invented as a catalog store ID.

The initial snapshot is `snapshots/foodlion/2026-09-08/manifest.json`. The normal catalog request returned HTTP 403; zero categories and zero products were collected. Store catalog ID remains null. Discovery is false and completion status is blocked. Every availability decision is unverified. This is not a complete inventory snapshot.

A verified local store-scoped category manifest can be processed by the implemented coordinator, parallel product shards, resumable state and finalizer. Direct automatic category discovery from the live site remains unverified and requires source-specific work once normal access is available. No protection was bypassed.

## Source accounting

Raw record counts differ from candidate file counts for files containing multiple recipes. Source decisions, exact commits, patterns and license evidence are in `config/recipe-sources.yaml`.

| Source | Decision | Raw recipes | Failed candidate files |
| --- | --- | ---: | ---: |
| [panozzaj--recipes](https://github.com/panozzaj/recipes) | enabled | 69 | 12 |
| [obfuscurity--food-recipes](https://github.com/obfuscurity/food-recipes) | enabled | 14 | 0 |
| [dolph--recipes](https://github.com/dolph/recipes) | enabled | 146 | 5 |
| [kmcconnell--recipyzer](https://github.com/kmcconnell/recipyzer) | blocked | 0 | 0 |
| [DEAD10C5--1337-Noms-The-Hacker-Cookbook](https://github.com/DEAD10C5/1337-Noms-The-Hacker-Cookbook) | enabled | 53 | 7 |
| [user24--auntiesrecipes](https://github.com/user24/auntiesrecipes) | blocked | 0 | 0 |
| [Anduin2017--HowToCook](https://github.com/Anduin2017/HowToCook) | enabled | 370 | 0 |
| [hendricius--the-bread-code](https://github.com/hendricius/the-bread-code) | enabled | 7 | 7 |
| [usmanayubsh--cooking-recipes](https://github.com/usmanayubsh/cooking-recipes) | blocked | 0 | 0 |
| [AshtarCodes--Con-Sazon](https://github.com/AshtarCodes/Con-Sazon) | not-a-recipe-source | 0 | 0 |
| [douvy--tasty-cooking](https://github.com/douvy/tasty-cooking) | enabled | 55 | 0 |
| [YunYouJun--cook](https://github.com/YunYouJun/cook) | unsupported | 0 | 0 |
| [aweijnitz--recipe-el_fuego_viviente](https://github.com/aweijnitz/recipe-el_fuego_viviente) | enabled | 1 | 4 |
| [hendricius--pizza-dough](https://github.com/hendricius/pizza-dough) | enabled | 1 | 0 |
| [sinker--tacofancy](https://github.com/sinker/tacofancy) | enabled | 70 | 93 |
| [buggymcbugfix--602f34214a37d972993830c2c9526cf0](https://gist.github.com/buggymcbugfix/602f34214a37d972993830c2c9526cf0) | enabled | 0 | 1 |
| [hendricius--the-sourdough-framework](https://github.com/hendricius/the-sourdough-framework) | unsupported | 0 | 0 |
| [andrewkern--bagels](https://github.com/andrewkern/bagels) | enabled | 0 | 1 |
| [frenchguycooking--doughsheeter](https://github.com/frenchguycooking/doughsheeter) | blocked | 0 | 0 |
| [karlomikus--bar-assistant](https://github.com/karlomikus/bar-assistant) | disabled | 0 | 0 |
| [AndreWohnsland--CocktailBerry](https://github.com/AndreWohnsland/CocktailBerry) | disabled | 0 | 0 |
| [alfg--opendrinks](https://github.com/alfg/opendrinks) | disabled | 0 | 0 |
| [clarklab--chowdown](https://github.com/clarklab/chowdown) | enabled | 36 | 1 |
| [domingoclub--fermenter-software](https://github.com/domingoclub/fermenter-software) | not-a-recipe-source | 0 | 0 |
| [Murgio--Food-Recipe-CNN](https://github.com/Murgio/Food-Recipe-CNN) | disabled | 0 | 0 |
| [pearofducks--foodprocessor](https://github.com/pearofducks/foodprocessor) | enabled | 1 | 0 |
| [grocy--grocy](https://github.com/grocy/grocy) | not-a-recipe-source | 0 | 0 |
| [hmontazeri--is-vegan](https://github.com/hmontazeri/is-vegan) | not-a-recipe-source | 0 | 0 |
| [mealie-recipes--mealie](https://github.com/mealie-recipes/mealie) | enabled | 19 | 3 |
| [kirmanak--Mealient](https://github.com/kirmanak/Mealient) | not-a-recipe-source | 0 | 0 |
| [eleow--IRS-MR-2019-07-01-IS1FT-GRP-MEWPlanner](https://github.com/eleow/IRS-MR-2019-07-01-IS1FT-GRP-MEWPlanner) | not-a-recipe-source | 0 | 0 |
| [schollz--meanrecipe](https://github.com/schollz/meanrecipe) | enabled | 928 | 680 |
| [nextcloud--cookbook](https://github.com/nextcloud/cookbook) | enabled | 9 | 17 |
| [steve71--RasPiBrew](https://github.com/steve71/RasPiBrew) | disabled | 0 | 0 |
| [bryceadams--Recipe-Hero](https://github.com/bryceadams/Recipe-Hero) | not-a-recipe-source | 0 | 0 |
| [Brooke-white--RecipeParser](https://github.com/Brooke-white/RecipeParser) | enabled | 113 | 1 |
| [reaper47--recipya](https://github.com/reaper47/recipya) | enabled | 321 | 97 |
| [dpapathanasiou--recipebook](https://github.com/dpapathanasiou/recipebook) | not-a-recipe-source | 0 | 0 |
| [TandoorRecipes--recipes](https://github.com/TandoorRecipes/recipes) | enabled | 22 | 5 |
| [dytlabs--Cook-It-Android-XML-Template](https://github.com/dytlabs/Cook-It-Android-XML-Template) | disabled | 0 | 0 |
| [mrezkys--hungry](https://github.com/mrezkys/hungry) | disabled | 0 | 0 |
| [dopebase--react-native-recipes-app](https://github.com/dopebase/react-native-recipes-app) | disabled | 0 | 0 |

## Remaining limitations

- BBC: 11,161 title/search records preserved in `state/recipes/bbc-index.jsonl`; remote bodies were not fetched because BBC robots rules expressly disallow the relevant AI-agent collection. Exact evidence is in `state/recipes/bbc-access.json`.
- YunYouJun/cook: video-reference metadata preserved in `state/recipes/yunyoujun-index.jsonl`; video instructions are unsupported, not falsely counted as full recipes.
- The Sourdough Framework: linked book format is unsupported by the current recipe adapters; recorded explicitly in source configuration.
- recipyzer and cooking-recipes clone access failed. The dough-sheeter link also failed but is a hardware source rather than a meal corpus. Full reasons are retained in configuration/discovery.
- Most remaining parse failures are legacy page extracts without clear ingredient/instruction sections, HTML formats the adapters do not support, incomplete recipe placeholders, and documentation/book material. These are parser/source-structure limitations, not all external access blocks. Original revision/path and failure reasons are preserved; cached bodies remain locally available for adapter improvements.
- Exact-match canonicalization is intentionally conservative, especially for multilingual ingredients, quantities embedded in prose, and product variants. Unresolved names and unsupported quantities must be checked at the source. The data is useful for browsing but is not a fully curated cooking corpus.
- For third-party or unknown-license sources, site pages omit expressive cooking prose and link to the source. Recipe facts and original links remain traceable. Local raw research data is not a public redistribution grant.
- Existing source revisions remain pinned. Adding new sources has an additive plan workflow; upgrading an existing source revision currently requires an explicitly versioned refresh design, not an automatic overwrite.

## Verification

- Formatting and linting passed; 50 automated tests passed.
- All persisted JSONL kinds, including raw/normalized products and recipes, match results, duplicate groups, BBC and video metadata indexes, are schema checked.
- Raw shard ownership is exclusive and checked centrally; no recipe candidate is owned by two agents.
- All three recipe shards were resumed without changing raw bytes. Tests also interrupt/resume Food Lion collection after a durable product, test failed-item recovery, immutable snapshots and idempotent merges.
- Normalized/raw provenance, product evidence references, snapshot and source manifests, and repeated matcher output are validated offline.
- Published cooking text contains no forbidden small-volume units; original URLs are preserved rather than rewritten when their domain/path happens to contain those words.
- Chromium checked 2,235 cards, three recipe pages, search/coverage filters, saved notes/cooked status, 390px mobile layout and zero browser errors. A real layout overflow was fixed before this report.

## Resume / retry

```sh
make resume
.venv/bin/python -m recipe_system.recipes shard --agent recipe-agent-03 --retry-failures
make extend-recipes collect-recipes   # after enabling newly reviewed sources
make pipeline
make serve
```

Retry failed files after improving an adapter; all successes are retained. Failed attempts and subsequent resolution events are recorded in shard state. Failure-history recording was added during initial collection; earlier recovery event timestamps were not retrospectively invented.
