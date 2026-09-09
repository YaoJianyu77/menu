# Personal recipe book

The homepage is the complete catalog: **2,556 recipes**, one search field, six combinable filters, sorting and pagination. Every title opens its existing static recipe detail page. No unique recipes were excluded, and no recipe identities or content changed.

The interface has no visible recommendation scores, score controls, dashboard sections or category navigation. Standalone category and recommendation pages are no longer generated. Categories are homepage filter choices: cuisine, meal type, main protein, cooking method, total time and Food Lion compatibility. Default order retains the existing internal practical ordering. Manual sorts are Default, Recipe Name, Total Time and Food Lion Compatibility; unknown times follow known times.

The build contains **2,643 HTML pages**: 2,556 recipe details, 54 static catalog pages (48 cards per page), and 33 redirects preserving old duplicate links. All recipes remain reachable through static pagination, including without JavaScript. Search/filtering works over the complete index. URL parameters retain the current controls and page; the detail back link restores these using tab-local session storage.

Cards and detail headers show title, optional image and time/cooking method in that order. Cuisine/meal-type labels and Food Lion percentages are omitted. Cuisine remains searchable/filterable, and compatibility filter options use qualitative labels with unchanged internal thresholds. The shared display-title helper removes terminal generic Chinese `做法` or `的做法`, without changing original or normalized source titles or recipe identifiers. **Zero recipes currently have permitted images**; no placeholders appear. Fixture tests verify valid-image ordering and image-free rendering. Detail pages show cooking information first, with notes collapsed and source attribution retained. Food Lion compatibility uses existing data.

## Unchanged publication limits

533 pages contain local cooking instructions; 2,023 link to the original recipe under the existing publication-permission rules. [Per-recipe decisions](catalog-publication.json) and [image audit](catalog-images.json) are unchanged. Collection, normalization, recipe content, Food Lion evidence and deterministic ranking are untouched.

## Validation

132 automated tests pass. Formatting, linting, static build, full persisted-data validation and deterministic matching checks pass. Catalog checks validate every recipe link, complete static reachability, filter membership, stable URLs, image permissions, score-free UI and metric cooking units. Chromium checks at 1366×900 and 390×844 cover full-dataset search, all six filters, combined filters, sorting, unknown time handling, pagination, back-link state, notes, no horizontal overflow and no browser errors. JavaScript-disabled browsing also passes.

See [browser validation](catalog-browser-validation.json) and [catalog validation](catalog-validation.json). GitHub Pages deploys successful pushes to `master`; the user authorized pushing and deploying this cleanup after validation.
