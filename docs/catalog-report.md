# Complete personal recipe catalog

- **2,556 recipes published, with 2,556 individual cooking pages.**
- **0 image-bearing recipes:** no persisted photo has sufficiently clear image-specific display rights. No artificial photographs or missing-image boxes are used.
- **35 cuisine categories, 14 meal types, 11 protein groups, 12 cooking methods, and 6 time groups.**
- Full-catalog title, ingredient, cuisine, meal-type, protein and method search; score, compatibility, time and category filters; score/compatibility/time/name sorting.
- Recommended remains separate from All Recipes. Lower scores, desserts, sides, snacks, condiments, baking and same-title variants remain discoverable.

All Recipes uses 54 statically navigable pages, up to 48 compact cards per page. Category pages likewise include all members and paginate where needed. Search uses a generated local JSON index and does not load long recipe instructions. Every title opens its stable cooking page. The home page links prominently to every browse mode and useful meal groups.

The build contains **3,005 HTML pages**: 2,556 recipe details, 416 home/listing/category pages, and 33 redirects preserving older duplicate-record links. Exact duplicate records remain in the original data; the catalog uses their final representatives. Similar titles remain separate unique recipes.

## Publication limitations

**No unique recipe pages were excluded.** Every unique recipe has an ingredient/metadata page and original-source attribution.

**533 pages include cooking instructions.** For **2,023 recipes**, the existing persisted redistribution permission is not established, so the page links to the original instructions instead of reproducing them. [Exact per-recipe decisions](catalog-publication.json) retain stable ID, source URL and reason. This pass did not alter licensing decisions or collect more source material.

The [image audit](catalog-images.json) records why no current photographs are displayed. Image availability never removes a recipe. Data-quality warnings on individual cooking pages remain concise; engineering collection diagnostics stay out of the catalog interface.

## Verification

- **129 automated tests pass**, including full catalog generation, stable URLs, card links, category membership, optional-image rendering and search completeness.
- Formatting, Python lint, JavaScript syntax and browser-script formatting pass.
- Offline checks confirm all 2,556 recipes are reachable, every card title targets the right detail page, all local links resolve, category membership is complete, and visible cooking text contains no forbidden small-volume unit spellings.
- Desktop and mobile Chromium checks pass for all search/filter/sort controls, pagination, five category axes, detail navigation and notes; no browser errors or horizontal overflow. See [browser report](catalog-browser-validation.json).
- Collection, normalization, deduplication and ranking data/models remain unchanged. The build is static, local and reproducible; no deployment or remote push was performed.
