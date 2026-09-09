# Single-page external recipe index

The website now generates **one HTML page**, the homepage. All **2,556 unique recipes** remain in the persisted catalog. Recipe titles open persisted original/source URLs in new tabs with `noopener noreferrer`. Invalid or missing source URLs produce non-clickable titles, never invented links; the validation report records their count. **Current missing/invalid URL count: 0.**

No recipe detail, category, recommendation, duplicate redirect or static pagination pages are generated. Detail-only rendering, image display and personal-notes JavaScript have been removed. The build clears obsolete generated output. Recipe source data, normalized data, IDs, ranking, title cleanup and provenance remain intact.

The dense three/two/one-column layout, 120-row client pagination, sticky controls, combined search/filters and browser-local hiding are preserved. Hidden management and recipe rows both use safe external links. Query parameters retain catalog state; no internal recipe-reading flow remains. Without JavaScript, all titles appear on the single homepage.

Validation covers safe persisted URLs, complete index membership, missing-URL handling, one HTML output, display-title cleanup, no images/scores/cuisine labels beside titles, search, filters, sorting, pagination, hiding, Undo, Restore and malformed storage. Browser tests intercept external navigations rather than request source content. See [catalog validation](catalog-validation.json) and [browser validation](catalog-browser-validation.json).

121 tests pass after replacing obsolete detail-page tests with single-page/external-link checks. Formatting, linting, build and full persisted-data validation pass. Chromium verifies desktop, tablet and mobile, including new-tab isolation, query state, hiding and JavaScript-disabled access to all titles.
