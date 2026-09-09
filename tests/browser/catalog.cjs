/* Run from the repository root; starts and stops its own loopback-only server. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { spawn } = require("node:child_process");
const base = (process.env.BASE_URL || "http://127.0.0.1:8000/").replace(
  /\/?$/,
  "/",
);
const index = JSON.parse(
  fs.readFileSync("site/dist/search-index.json", "utf8"),
);
const lookup = new Map(index.map((row) => [row.id, row]));
const checks = [];
const server = process.env.BASE_URL
  ? null
  : spawn(
      "python3",
      [
        "-m",
        "http.server",
        "8000",
        "--bind",
        "127.0.0.1",
        "--directory",
        "site/dist",
      ],
      { stdio: "ignore" },
    );
(async () => {
  let browser;
  try {
    for (let attempt = 0; attempt < 50; attempt++) {
      if (server && server.exitCode !== null)
        throw Error("Could not start dedicated catalog server");
      try {
        if ((await fetch(base)).ok) break;
      } catch {
        /* Wait for startup. */
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({ headless: true });
    for (const viewport of [
      { width: 1366, height: 900 },
      { width: 390, height: 844 },
    ]) {
      const context = await browser.newContext({ viewport });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("response", (response) => {
        if (
          response.url().startsWith(new URL(base).origin) &&
          response.status() >= 400
        )
          errors.push(`${response.status()} ${response.url()}`);
      });
      page.on("request", (request) => {
        const url = new URL(request.url());
        if (url.origin === new URL(base).origin)
          assert(
            url.pathname.startsWith(new URL(base).pathname),
            `Outside base path: ${url}`,
          );
      });
      const go = async (path) => {
        const response = await page.goto(base + path);
        assert.equal(response.status(), 200);
        await page
          .locator('#catalog-config[data-loaded="true"]')
          .waitFor({ state: "attached" });
      };
      const ids = () =>
        page
          .locator("#catalog-results .card")
          .evaluateAll((cards) => cards.map((card) => card.dataset.recipeId));
      const checkRows = async (predicate) => {
        const visible = await ids();
        assert(visible.length > 0);
        assert(visible.every((id) => predicate(lookup.get(id))));
      };
      const reset = () => page.locator("#catalog-reset").click();
      await go("recipes/index.html");
      assert.equal(index.length, 2556);
      assert(
        (await page.locator("#catalog-count").textContent()).includes("2,556"),
      );
      assert.deepEqual(
        await ids(),
        index.slice(0, 48).map((row) => row.id),
      );
      assert.equal(
        await page.locator("#catalog-results img").count(),
        index.slice(0, 48).filter((row) => row.image).length,
      );
      const links = await page
        .locator("#catalog-results .card")
        .evaluateAll((cards) =>
          cards.map((card) => ({
            id: card.dataset.recipeId,
            url: card.querySelector("h2 a").href,
          })),
        );
      assert(
        links.every((link) => link.url === base + lookup.get(link.id).url),
      );
      await page.getByRole("button", { name: "Next", exact: true }).click();
      assert.deepEqual(
        await ids(),
        index.slice(48, 96).map((row) => row.id),
      );
      await go("recipes/page-2.html");
      assert.deepEqual(
        await ids(),
        index.slice(48, 96).map((row) => row.id),
      );
      const distant = index.find(
        (row, i) =>
          i > 500 &&
          row.title.length > 10 &&
          index.filter((other) => other.title === row.title).length === 1,
      );
      await page.locator("#catalog-search").fill(distant.title);
      assert((await ids()).includes(distant.id));
      await reset();
      await page.locator("#catalog-search").fill("chicken");
      await checkRows((row) =>
        [
          row.title,
          row.cuisine,
          row.meal_type,
          ...row.ingredients,
          ...row.proteins,
          ...row.methods,
        ]
          .join(" ")
          .toLowerCase()
          .includes("chicken"),
      );
      await reset();
      for (const [key, value, predicate] of [
        ["cuisine", "American", (row) => row.cuisines.includes("American")],
        ["meal_type", "Dessert", (row) => row.meal_type === "Dessert"],
        ["protein", "Chicken", (row) => row.proteins.includes("Chicken")],
        ["method", "Oven", (row) => row.methods.includes("Oven")],
      ]) {
        await page
          .locator(`[data-catalog-filter="${key}"]`)
          .selectOption(value);
        await checkRows(predicate);
        await reset();
      }
      for (const [key, value, predicate] of [
        ["min-score", "80", (row) => row.score >= 80],
        ["max-score", "59", (row) => row.score <= 59],
        [
          "coverage",
          "85",
          (row) => row.coverage != null && row.coverage >= 0.85,
        ],
        [
          "total",
          "30",
          (row) => row.total_minutes != null && row.total_minutes <= 30,
        ],
      ]) {
        await page.locator(`[data-catalog-filter="${key}"]`).fill(value);
        await checkRows(predicate);
        await reset();
      }
      for (const sort of ["name", "coverage", "time"]) {
        await page.locator("#catalog-sort").selectOption(sort);
        const actual = (await ids()).map((id) => lookup.get(id));
        for (let i = 1; i < actual.length; i++) {
          if (sort === "name")
            assert(actual[i - 1].sort_title <= actual[i].sort_title);
          if (sort === "coverage")
            assert(
              (actual[i - 1].coverage ?? -1) >= (actual[i].coverage ?? -1),
            );
          if (sort === "time")
            assert(
              (actual[i - 1].total_minutes ?? Infinity) <=
                (actual[i].total_minutes ?? Infinity),
            );
        }
      }
      // Unknown times must follow all known times, including on the final page.
      while (
        !(await page
          .getByRole("button", { name: "Next", exact: true })
          .isDisabled())
      )
        await page.getByRole("button", { name: "Next", exact: true }).click();
      assert((await ids()).every((id) => lookup.get(id).total_minutes == null));
      await reset();
      await page.locator("#catalog-search").fill("zz-no-recipe-exists-zz");
      assert.equal((await ids()).length, 0);
      assert(
        await page
          .getByText("No recipes match these filters.", { exact: false })
          .isVisible(),
      );
      for (const [axis, field] of [
        ["cuisine", "cuisines"],
        ["meal-type", "meal_type"],
        ["protein", "proteins"],
        ["method", "methods"],
        ["time", "time_categories"],
      ]) {
        await page.goto(base + axis + "/index.html");
        await page.locator(".category-list a").first().click();
        await page
          .locator('#catalog-config[data-loaded="true"]')
          .waitFor({ state: "attached" });
        const scope = await page
          .locator("#catalog-config")
          .evaluate((node) => JSON.parse(node.textContent).scope);
        await checkRows((row) =>
          Array.isArray(row[field])
            ? row[field].includes(scope.value)
            : row[field] === scope.value,
        );
        const expected = index.filter((row) =>
          Array.isArray(row[field])
            ? row[field].includes(scope.value)
            : row[field] === scope.value,
        ).length;
        assert(
          (await page.locator("#catalog-count").textContent()).startsWith(
            expected.toLocaleString() + " recipes",
          ),
        );
      }
      await go("recommended/index.html");
      await checkRows(
        (row) => row.everyday_eligible && row.discovery_representative,
      );
      await page.goto(base + index[0].url);
      assert.equal(await page.locator("h1").textContent(), index[0].title);
      const headings = await page.locator("h2").allTextContents();
      assert(
        headings.indexOf("Ingredients") < headings.indexOf("Instructions"),
      );
      assert(
        headings.indexOf("Instructions") <
          headings.indexOf("Food Lion ingredients"),
      );
      assert(
        !/\b(?:tsp|tbsp|teaspoons?|tablespoons?)\b/i.test(
          await page
            .locator(".ingredients,.steps")
            .allTextContents()
            .then((items) => items.join(" ")),
        ),
      );
      assert(
        await page.getByText("Local stock may vary.", { exact: false }).count(),
      );
      await page.locator('[name="notes"]').fill("Catalog browser verification");
      await page.locator('#personal-form button[type="submit"]').click();
      await page.reload();
      assert.equal(
        await page.locator('[name="notes"]').inputValue(),
        "Catalog browser verification",
      );
      for (const path of ["index.html", "recipes/index.html", index[0].url]) {
        await page.goto(base + path);
        if (path === "recipes/index.html") {
          await page
            .locator('#catalog-config[data-loaded="true"]')
            .waitFor({ state: "attached" });
          await page.screenshot({
            path: `/tmp/menu-catalog-${viewport.width}.png`,
          });
        }
        assert(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth + 1,
          ),
          `Horizontal overflow: ${path}`,
        );
      }
      assert.deepEqual(errors, []);
      checks.push({
        viewport,
        status: "passed",
        checks: [
          "complete_catalog",
          "title_and_ingredient_search",
          "all_filters",
          "sorts_unknown_time_last",
          "pagination_and_direct_page_2",
          "five_category_axes",
          "card_links",
          "no_image_layout",
          "detail_cooking_order",
          "metric_instructions",
          "personal_notes",
          "mobile_overflow",
          "no_browser_errors",
        ],
      });
      await context.close();
    }
    fs.writeFileSync(
      process.env.BROWSER_REPORT || "docs/catalog-browser-validation.json",
      JSON.stringify(
        {
          status: "passed",
          base_url: base,
          recipes: index.length,
          images: index.filter((row) => row.image).length,
          checks,
        },
        null,
        2,
      ) + "\n",
    );
    console.log(
      JSON.stringify({
        status: "passed",
        viewports: checks.length,
        recipes: index.length,
      }),
    );
  } finally {
    await browser?.close();
    server?.kill();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
