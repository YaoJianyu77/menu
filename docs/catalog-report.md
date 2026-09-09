# Dense personal recipe directory

All **2,556 recipes** remain accessible. The homepage uses compact 36-pixel rows, three columns on wide desktops, two on tablets and one on phones. Titles are primary; desktop time/method text is muted, and mobile omits it. No catalog photographs, card boxes, cuisine labels, percentages or scores are rendered, including for recipes with permitted images. Detail pages retain their cooking layout and image support.

A short sticky bar contains search, five dropdown filters (Type, Protein, Method, Time, Cuisine), Default/Name/Time sorting and Clear. Searches and combined filters cover the complete dataset. Count updates, URL state, keyboard navigation and stateful back links remain supported. Long titles remain available through tooltips and remain keyboard accessible without row movement.

There are **22 static directory pages**, up to **120 recipes per page**, 2,556 unchanged detail URLs and 33 historical duplicate redirects: **2,611 HTML pages** total. Every recipe is also reachable without JavaScript. No unique recipes were excluded. Collection, normalization, ranking, source records, displayed title cleanup and source permissions are unchanged.

134 tests pass (including the Node preference-store suite). Formatting, linting, full static build, persisted-data validation and deterministic matching checks pass. Chromium checks cover desktop (1366×900), tablet (900×900) and mobile (390×844), including measured column counts, row height, visible title density, sticky controls, keyboard focus, search, combined filters, sorting, pagination, back links, no directory images and no horizontal overflow. See [browser report](catalog-browser-validation.json) and [catalog validation](catalog-validation.json).

The existing publication rules still provide local instructions for 533 recipes and source links for 2,023. Photos remain optional on detail pages; none currently has permitted photo data. The user authorized pushing and deploying this catalog redesign after validation.

## Browser-local hiding

Rows now include a small accessible × control. Hidden IDs are stored under `my-recipes:hidden:v1`; hiding never changes the static dataset or source records. Undo, a Hidden management panel, individual restoration and Restore all work across the complete catalog. Search, counts, filters and pagination exclude hidden IDs; Clear does not restore them. The detail-page action uses the same storage and returns to the catalog with Undo available. Preferences persist per browser and origin, without cross-device synchronization. Malformed values and IDs missing from the current dataset are safe.
