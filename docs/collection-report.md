# Data completeness and quality report

Baseline: commit `ff8cf82`. This pass continues the existing architecture. No deployment or remote push was performed. Machine-readable counts are in [pass-metrics.json](pass-metrics.json).

## Before and after

| Measure | Before | After |
| --- | ---: | ---: |
| Raw recipe records | 2,235 | 2,589 |
| Normalized recipe records | 2,235 | 2,589 |
| Candidate files attempted | 3,167 | 3,219 |
| Candidate files successfully parsed | 2,233 | 2,471 |
| Explicit failed candidate files | 934 | 748 |
| Duplicate records grouped, retained | 16 | 33 |
| Normalized unique representatives | 2,219 | 2,556 |
| Static pages | 2,236 | 2,590 |
| Explicit active cooking time | 0 | 15 |
| Explicit total time | 304 | 650 |
| Food Lion canonical ingredients with evidence | 0 | 155 likely |
| Configured-store verified ingredients | 0 | 0 |

The gain is **354 raw recipes**: 212 from recovery of original failures and 142 from newly enumerated source fixtures/archive members and one previously missed quoted filename. A candidate file can contain multiple recipes, so file and recipe counts differ. All original 2,235 raw records remain unchanged. The historical blocked Food Lion snapshot is also unchanged; [data-integrity.json](data-integrity.json) records the checks and idempotent merge hash.

Normalization completed without exceptions. **399 recipes retain explicit normalization quality issues**, and the matcher flags **416** after additional structural checks. Nine of the 212 recovered records retain normalization issues: recovery means a raw parse was preserved, not that a recipe became cooking-ready. These records are quarantined from recommendation. All variants and 27 multi-record duplicate groups remain stored; 33 duplicate records share 2,556 stable representatives.

## Exact recovery accounting

The original 934 failures have this disjoint final classification:

| Outcome | Files |
| --- | ---: |
| Recovered | 212 |
| Remaining legitimate recipe failures | 134 |
| Confirmed non-recipe candidates | 12 |
| Unsupported/ambiguous source structure | 480 |
| Captured blocked/access-error content | 96 |
| **Total** | **934** |

Thus 722 original failures remain recorded; unsupported plus blocked is 576. The additional 52 candidates include 26 failed files, yielding 748 current failed candidates overall. Failure records include deliberate nonrecipe exclusions rather than silently deleting them. These categories are file outcomes, not an invented count of undiscovered recipes.

The [machine-readable root-cause breakdown](../state/recipes/recovery/breakdown.json) covers all 934: HTML 113; alternate Markdown layouts 74; captured access/missing pages 96; duplicate/nonrecipe files 3; incomplete cached content 64; instruction parsing 198; other 55; repository metadata 9; unlabelled/index archives 322. [Baseline](../state/recipes/recovery/baseline.jsonl), [outcomes](../state/recipes/recovery/outcomes.jsonl), per-shard improvement reports and checkpoint histories preserve previous errors, revisions, recovered IDs and later decisions.

Generalized fixes cover Markdown headings/bullets/tables, bounded archived text sections, named HTML recipe components, CSV exports, OCR JSON, multiple structured recipes, ZIP/nested recipe exports, Paprika and Cookn table joins. NUL-safe Git enumeration recovered the omitted quoted filename. No individual recipe was manually fabricated. Nine Mealie backups contain 1,021 anonymized recipe-shaped rows whose 24,156 text fields were erased by the source's anonymizer; these are not recipes. Two PlanToEat fixtures contain explicit placeholder cooking content. All 11 are documented nonrecipes in [new-source-failures.jsonl](../state/recipes/recovery/new-source-failures.jsonl), not inflated recovery counts. See [parser-recovery.md](parser-recovery.md) for adapter scope and limits.

## Source coverage

All 42 current indexed source decisions were reviewed: **8 COMPLETE, 12 PARTIAL, 4 BLOCKED, 16 NOT_A_RECIPE_SOURCE, 2 UNSUPPORTED**. The 20 enabled sources have all 3,219 declared files accounted for; zero pending candidates, ownership collisions or identified unexplored candidate gaps remain in the pinned trees. This does **not** establish complete recipe extraction: 12 enabled sources retain failed files or nested members. Overall recipe status is **PARTIAL**. Source revisions remain pinned; scope decisions and excluded paths are explicit.

[Source coverage](source-coverage.json) records estimates, selected/auxiliary/excluded paths, blocked counts, complete/partial decisions and archive-member failures for every source. [Global manifest](../state/recipes/manifest.json) separates candidate accounting from source extraction completeness. “Successful” below means candidate files; raw records can be more numerous.

| Source | Config decision | Coverage | Candidates | Successful | Failed | Raw records |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| [panozzaj--recipes](https://github.com/panozzaj/recipes) | enabled | PARTIAL | 81 | 75 | 6 | 75 |
| [obfuscurity--food-recipes](https://github.com/obfuscurity/food-recipes) | enabled | COMPLETE | 14 | 14 | 0 | 14 |
| [dolph--recipes](https://github.com/dolph/recipes) | enabled | PARTIAL | 151 | 146 | 5 | 146 |
| [kmcconnell--recipyzer](https://github.com/kmcconnell/recipyzer) | blocked | BLOCKED | 0 | 0 | 0 | 0 |
| [DEAD10C5--1337-Noms-The-Hacker-Cookbook](https://github.com/DEAD10C5/1337-Noms-The-Hacker-Cookbook) | enabled | PARTIAL | 60 | 57 | 3 | 57 |
| [user24--auntiesrecipes](https://github.com/user24/auntiesrecipes) | blocked | BLOCKED | 0 | 0 | 0 | 0 |
| [Anduin2017--HowToCook](https://github.com/Anduin2017/HowToCook) | enabled | COMPLETE | 370 | 370 | 0 | 370 |
| [hendricius--the-bread-code](https://github.com/hendricius/the-bread-code) | enabled | PARTIAL | 14 | 11 | 3 | 11 |
| [usmanayubsh--cooking-recipes](https://github.com/usmanayubsh/cooking-recipes) | blocked | BLOCKED | 0 | 0 | 0 | 0 |
| [AshtarCodes--Con-Sazon](https://github.com/AshtarCodes/Con-Sazon) | not-a-recipe-source | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [douvy--tasty-cooking](https://github.com/douvy/tasty-cooking) | enabled | COMPLETE | 55 | 55 | 0 | 55 |
| [YunYouJun--cook](https://github.com/YunYouJun/cook) | unsupported | UNSUPPORTED | 0 | 0 | 0 | 0 |
| [aweijnitz--recipe-el_fuego_viviente](https://github.com/aweijnitz/recipe-el_fuego_viviente) | enabled | PARTIAL | 5 | 1 | 4 | 1 |
| [hendricius--pizza-dough](https://github.com/hendricius/pizza-dough) | enabled | COMPLETE | 1 | 1 | 0 | 1 |
| [sinker--tacofancy](https://github.com/sinker/tacofancy) | enabled | PARTIAL | 163 | 115 | 48 | 115 |
| [buggymcbugfix--602f34214a37d972993830c2c9526cf0](https://gist.github.com/buggymcbugfix/602f34214a37d972993830c2c9526cf0) | enabled | COMPLETE | 1 | 1 | 0 | 1 |
| [hendricius--the-sourdough-framework](https://github.com/hendricius/the-sourdough-framework) | unsupported | UNSUPPORTED | 0 | 0 | 0 | 0 |
| [andrewkern--bagels](https://github.com/andrewkern/bagels) | enabled | COMPLETE | 1 | 1 | 0 | 1 |
| [frenchguycooking--doughsheeter](https://github.com/frenchguycooking/doughsheeter) | blocked | BLOCKED | 0 | 0 | 0 | 0 |
| [karlomikus--bar-assistant](https://github.com/karlomikus/bar-assistant) | disabled | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [AndreWohnsland--CocktailBerry](https://github.com/AndreWohnsland/CocktailBerry) | disabled | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [alfg--opendrinks](https://github.com/alfg/opendrinks) | disabled | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [clarklab--chowdown](https://github.com/clarklab/chowdown) | enabled | PARTIAL | 37 | 36 | 1 | 36 |
| [domingoclub--fermenter-software](https://github.com/domingoclub/fermenter-software) | not-a-recipe-source | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [Murgio--Food-Recipe-CNN](https://github.com/Murgio/Food-Recipe-CNN) | disabled | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [pearofducks--foodprocessor](https://github.com/pearofducks/foodprocessor) | enabled | COMPLETE | 1 | 1 | 0 | 1 |
| [grocy--grocy](https://github.com/grocy/grocy) | not-a-recipe-source | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [hmontazeri--is-vegan](https://github.com/hmontazeri/is-vegan) | not-a-recipe-source | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [mealie-recipes--mealie](https://github.com/mealie-recipes/mealie) | enabled | PARTIAL | 42 | 28 | 14 | 144 |
| [kirmanak--Mealient](https://github.com/kirmanak/Mealient) | not-a-recipe-source | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [eleow--IRS-MR-2019-07-01-IS1FT-GRP-MEWPlanner](https://github.com/eleow/IRS-MR-2019-07-01-IS1FT-GRP-MEWPlanner) | not-a-recipe-source | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [schollz--meanrecipe](https://github.com/schollz/meanrecipe) | enabled | PARTIAL | 1609 | 1076 | 533 | 1076 |
| [nextcloud--cookbook](https://github.com/nextcloud/cookbook) | enabled | PARTIAL | 47 | 23 | 24 | 23 |
| [steve71--RasPiBrew](https://github.com/steve71/RasPiBrew) | disabled | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [bryceadams--Recipe-Hero](https://github.com/bryceadams/Recipe-Hero) | not-a-recipe-source | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [Brooke-white--RecipeParser](https://github.com/Brooke-white/RecipeParser) | enabled | COMPLETE | 115 | 115 | 0 | 115 |
| [reaper47--recipya](https://github.com/reaper47/recipya) | enabled | PARTIAL | 425 | 323 | 102 | 325 |
| [dpapathanasiou--recipebook](https://github.com/dpapathanasiou/recipebook) | not-a-recipe-source | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [TandoorRecipes--recipes](https://github.com/TandoorRecipes/recipes) | enabled | PARTIAL | 27 | 22 | 5 | 22 |
| [dytlabs--Cook-It-Android-XML-Template](https://github.com/dytlabs/Cook-It-Android-XML-Template) | disabled | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [mrezkys--hungry](https://github.com/mrezkys/hungry) | disabled | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |
| [dopebase--react-native-recipes-app](https://github.com/dopebase/react-native-recipes-app) | disabled | NOT_A_RECIPE_SOURCE | 0 | 0 | 0 | 0 |

BBC remains robots-blocked; its 11,161 saved title/search entries are metadata, not collected recipe bodies. Captured historical access errors were inspected offline without bypassing current controls. Other inaccessible repositories, video-only YunYouJun material and the unsupported Sourdough Framework book remain documented. Remaining parser failures are not all network blocks: ambiguous archives, incomplete caches, HTML layouts and missing recipe sections still require generalized adapters or better source data.

## Food Lion evidence capability

The configured store remains **1234 Richmond Road, Williamsburg, VA 23185**; its ecommerce store ID and inventory remain unverified. Other Food Lion stores are authorized evidence sources, but never silently replace the configured store or establish Richmond Road stock.

The direct inventory interface returned HTTP 403. A separate first-party [public grocery catalog](https://foodlion.com/groceries/) is explicitly permitted by Food Lion's robots rules. Normal requests collected all three advertised product sitemaps: **22,994 real product IDs/URLs**, plus **2,866 category URLs**. The all-aisles listing supplies **518 joined structured product names**. Remaining names are null; slugs are preserved separately. No product prices, stock, brands or package sizes were invented. Two additional listing entries fall outside this sitemap enumeration; product/category detail pages were not exhaustively collected, so even this is a bounded catalog observation, not exhaustive national inventory.

Explicit conservative prefix mappings connect **155 canonical ingredients to 239 real catalog products**, with URL, raw sitemap, retrieval timestamp, mapping method and national specificity. These support **Likely available**, not Verified. Exact Richmond Road availability, prices and orderability cannot be established. **Zero verified available and zero verified unavailable ingredients** are asserted. Unknown is not displayed or scored as unavailable. [Food Lion evidence documentation](foodlion-evidence.md) and the [evidence manifest](../data/foodlion/evidence/manifest.json) record exact collection scope and constraints. Historical inventory snapshots remain separate.

## Matching and recommendation review

There are **4 provisional recommendations**, **0 verified-store approvals**, 1,290 needs-review records and 1,299 rejected records. Every one of the 2,589 recipes has a stored result. Rejected recipes remain browseable. Provisional recommendations are Chickpea Salad, Sheet Pan Chicken and Sweet Potatoes, Western Omelet, and Spicy Kimchi Quinoa Bowls; exact source titles/IDs and review findings are in [normalization-audit.json](normalization-audit.json). They remain caveated: ingredient presence does not establish nutritional portions, and unknown active effort must be checked. Kimchi Quinoa additionally uses multiple vessels and precooked quinoa.

Unknown stock evidence is excluded from the availability scoring denominator; explicit absence would receive zero credit. Catalog and verified-store coverage, evidence confidence, product IDs, time/meal-balance/simplicity scores and score adjustments are persisted separately. [README ranking formula](../README.md#deterministic-ranking) specifies the reproducible calculation. Unknown cooking time receives no free credit. An explicit total within the active-time budget supports an upper bound without inventing active minutes.

The review inspected all requested cohorts: top 20 overall, top 10 Italian, French (7 available), Turkish/Mediterranean (4 available), Chinese/Asian, air fryer, under 20 minutes, and 10 low-scoring rejected recipes: **81 selections across 65 unique recipes**. Source-derived Asian associations are labelled rather than invented cuisine. The persisted audit includes per-row findings and earlier review history.

General fixes prevent desserts/dips/condiments and recipe components from ranking as complete meals; distinguish dishes served in sauce; reduce unsupported protein/vegetable or rich-ingredient claims; quarantine timing contradictions, advance preparation, sparse/contaminated ingredient lists and frequency aggregates; preserve package counts and sizes; normalize foreign measures and Unicode fractions; and avoid duplicate recommendation flooding. Remaining malformed extraction is flagged and rejected, not presented as curated cooking instructions. Multilingual and obscure ingredient canonicalization is still incomplete.

## Verification

- Formatting, Python linting and JavaScript syntax checks pass; **98 automated tests pass**.
- Full offline pipeline builds **2,590 pages**. Persisted raw/normalized/evidence/match/recovery/duplicate JSONL records are schema-validated.
- Provenance, actual Food Lion product references, exclusive shard ownership, snapshot/source manifests and deterministic matcher reproducibility pass; see [validation.json](validation.json).
- All seven collection shards resumed without retries and retained identical raw SHA-256 hashes; [resume verification](../state/recipes/recovery/resume-verification.json). Idempotent merge and original-record immutability also pass.
- Published cooking fields and rendered text contain no forbidden small-volume unit spellings; original source URLs are preserved separately.
- Real Chromium desktop/mobile checks cover browsing, search, catalog/verified labels, duplicate visibility, recipe pages, local annotations and overflow, with zero browser errors; [browser-validation.json](browser-validation.json).

Full source prose is published only where the source grant was affirmatively assessed. Other pages retain structured facts, provenance and original links. Unknown source licenses and source-derived nutrition remain unknown. No access restrictions were bypassed, and no retail competitor was used as Food Lion availability evidence.

## Reproduce or continue

```sh
make format lint test
make rebuild-evidence
make pipeline
make serve
# After generalized parser changes, retry only the affected idle shard:
.venv/bin/python -m recipe_system.recovery retry --agent recipe-agent-03
make audit-recipes
# After explicitly enabling additional source paths:
make extend-recipes collect-recipes
```

Keep failed-source caches for adapter development. Every original failure remains traceable to a pinned repository path; new successful parses append to their existing owner, while newly discovered paths receive independent shards. Preferences or site changes do not require source recollection.
