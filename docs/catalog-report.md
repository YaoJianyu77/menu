# Dense recipe directory with local cooking pages

The catalog publishes all **2,556 unique recipes** and **2,556 stable local detail pages** (2,557 HTML pages total). No recipe is excluded and no original-source URL is missing. Title links open local pages; the adjacent ↗ opens the recorded source directly in a safe new tab. Category and recommendation pages are not generated.

Ingredients remain available locally for every recipe. Redistribution permissions allow local instructions for 533 recipes; the other 2,023 show ingredients and a clear original-recipe link. No invented instructions or photographs are added. There are currently no permitted persisted recipe images. Source/normalized data, IDs, scores and source URLs remain unchanged.

Ingredient search includes canonical names, existing configured aliases, original ingredient text and original/display titles. Multiple ingredient phrases use deterministic AND matching, with exact/strong titles followed by ingredient relevance and then metadata relevance. Search and five filters combine across the full non-hidden dataset before 120-row pagination.

The desktop/tablet/mobile directory remains three/two/one columns, with compact rows, sticky filters and separate title/source/hide controls. Hidden preferences use browser-local stable IDs; Undo, Restore and Restore all remain available. Query state survives a local detail-page round trip. Scores, compatibility percentages, cuisine labels and images are absent from rows.

Validation covers stable local URLs, safe original-source icons, metric ingredients/instructions, permitted prose, original title preservation, alias and multiple ingredient search, complete catalog reachability, filtering, sorting, pagination and hiding. Chromium checks desktop, tablet and mobile, including source-icon isolation, keyboard access, state restoration and JavaScript-disabled access to every title. See [catalog validation](catalog-validation.json) and [browser validation](catalog-browser-validation.json).

125 automated tests pass. Formatting, linting, persisted-schema validation, deterministic matching checks and the 2,557-page static build pass. Browser validation covers the GitHub Pages `/menu/` base path at desktop, tablet and mobile widths. The tested desktop viewport displays 60 recipe titles in compact 37 px rows; optional metadata is hidden when it would crowd the title.
