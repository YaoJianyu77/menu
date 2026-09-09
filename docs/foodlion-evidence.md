# Food Lion evidence capability

The selected store remains **1234 Richmond Road, Williamsburg, VA 23185**.
Its inventory catalog ID is still unknown. No local stock, price or orderability
has been verified. Other Food Lion stores can supply likelihood evidence without
changing this selection; availability at another store is never Richmond Road
verification.

The initial HTTP 403 applied to the root/store inventory interface. Food Lion also
publishes a deliberately public [SEO grocery catalog](https://foodlion.com/groceries/).
Its [robots policy](https://foodlion.com/robots.txt) explicitly permits `/groceries/`
for AI clients and advertises the [catalog sitemap](https://foodlion.com/groceries/sitemap.xml).
Normal requests using `PersonalRecipeResearch/1.0` returned HTTP 200. No credentials,
browser impersonation, challenges, private APIs or protected best-price links were used.
Public search and normal browsing independently exposed these first-party pages.

This pass preserved all three advertised product sitemaps: **22,994 unique product
URLs and real catalog IDs**, plus **2,866 category URLs**. One public All Aisles
page contains 520 structured product names; **518** join the preserved product
sitemaps. The other two listing entries are outside this sitemap enumeration, so
the advertised sitemap scope is not claimed to cover every possible product.
Product names without structured evidence remain null, and URL slugs are retained
separately. We do not claim 22,994 product-detail pages were fetched. Category
detail pages have not been exhaustively explored. The exploratory Roma tomato
page also showed a real product title and ingredients, but that browser observation
is not used as a separate persisted inventory record.

**155 canonical ingredients map conservatively to 239 real catalog products.** The
mapping is reproducible from explicit product-slug prefixes in
`config/foodlion-evidence.yaml`; the prefix must immediately precede a numeric
package size. This prevents incidental ingredient words in prepared products from
establishing ingredient availability. For example, vegetable oil spread is not
evidence for cooking oil. Unmapped products are retained for future mapping.

Every mapped ingredient includes product IDs, original product URL, sitemap URL,
immutable raw file, observation timestamp, method and national-catalog specificity.
National catalog evidence yields **likely_available**, never **verified_available**.
It cannot establish Richmond Road shelf stock or current prices. `availability`,
store ID, price, brand and package size remain null when not independently extracted.
Sitemap facts and the one listing are archived under `data/foodlion/evidence/raw/`;
the manifest records counts, source URLs, HTTP status and content hashes. Existing
historical store snapshots were not modified.

The reusable classification helper additionally supports directly evidenced stock
at the configured store (`verified_available`), explicit out-of-stock evidence at
that store (`unavailable`), and insufficient evidence (`unknown`). An absent catalog
match is **unknown**, not evidence that Food Lion does not sell an ingredient.
This module's catalog normalization only emits likelihood records. The matcher
combines them with any independently verified snapshot and exposes each evidence
class separately.

Rebuild or validate the evidence offline:

```sh
.venv/bin/python -m recipe_system.evidence rebuild .
.venv/bin/python -m recipe_system.evidence validate .
```

Collect another observation into a **new** directory (the argument is a destination,
not the repository root):

```sh
.venv/bin/python -m recipe_system.evidence collect data/foodlion/evidence-next
```

The collector caches each successful response atomically, resumes existing cached
files, respects robots, sleeps between requests, and stops with a persisted failure
on access errors. It enumerates only sitemap URLs actually advertised by Food Lion.
New observations must be reviewed/imported explicitly; collecting into a new
directory never silently changes the active evidence or selected store. Its
completion flag means public sitemap discovery only, not complete inventory.

The second offline mapping pass expanded from 53 to 155 canonical ingredients,
using the already collected catalog without new source requests. The remaining
15 vocabulary entries stay unknown, including cuisine-specific sauces, fresh
herbs whose exact form is unresolved, and dietary-specific chocolate. Tamari does
not silently substitute for Chinese dark soy sauce, and generic Western cooking
wine does not establish Shaoxing wine availability. The mapping audit lists every
unmapped canonical entry.
