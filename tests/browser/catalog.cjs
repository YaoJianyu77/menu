/* Local Chromium checks; BASE_URL also supports a mounted project subpath. */
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
const lookup = new Map(index.map((r) => [r.id, r]));
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
  const checks = [];
  try {
    for (let n = 0; n < 50; n++) {
      if (server && server.exitCode !== null)
        throw Error("Catalog server failed");
      try {
        if ((await fetch(base)).ok) break;
      } catch {
        /* startup */
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
      page.on("pageerror", (e) => errors.push(e.message));
      page.on("response", (r) => {
        if (r.url().startsWith(base) && r.status() >= 400)
          errors.push(`${r.status()} ${r.url()}`);
      });
      page.on("request", (r) => {
        const u = new URL(r.url());
        if (
          u.origin === new URL(base).origin &&
          !u.pathname.startsWith(new URL(base).pathname)
        )
          errors.push(`Outside base: ${u}`);
      });
      const ready = () =>
        page
          .locator('#catalog-config[data-loaded="true"]')
          .waitFor({ state: "attached" });
      const go = async (path = "index.html") => {
        assert.equal((await page.goto(base + path)).status(), 200);
        await ready();
      };
      const ids = () =>
        page
          .locator("#catalog-results .card")
          .evaluateAll((cards) => cards.map((c) => c.dataset.recipeId));
      const reset = () =>
        page
          .getByRole("button", { name: "Clear filters", exact: true })
          .click();
      const filter = (key) => page.locator(`[data-catalog-filter="${key}"]`);
      const expected = async (rows) => {
        assert.deepEqual(
          await ids(),
          rows.slice(0, 48).map((r) => r.id),
        );
        assert.equal(
          await page.locator("#catalog-count").textContent(),
          `${rows.length.toLocaleString()} recipes`,
        );
      };
      await go();
      assert.equal(index.length, 2556);
      assert.equal(await page.locator("h1").textContent(), "My Recipes");
      await expected(index);
      assert.equal(await page.locator(".site-nav").count(), 0);
      assert.equal(await page.locator("[data-catalog-filter]").count(), 6);
      assert.deepEqual(
        await page.locator("#catalog-sort option").allTextContents(),
        ["Default", "Recipe Name", "Total Time", "Food Lion Compatibility"],
      );
      assert(
        !/recommendation|\bscore\b|\branking\b|\d+\/100/i.test(
          await page.locator("body").innerText(),
        ),
      );
      assert(!index.some((r) => "score" in r || "rank" in r));
      const links = await page
        .locator(".card h2 a")
        .evaluateAll((nodes) => nodes.map((a) => a.href));
      assert.deepEqual(
        links,
        index.slice(0, 48).map((r) => base + r.url),
      );
      assert.equal(await page.locator(".card img").count(), 0);
      await page.getByRole("button", { name: "Next", exact: true }).click();
      assert.deepEqual(
        await ids(),
        index.slice(48, 96).map((r) => r.id),
      );
      await go("page-2.html");
      assert.deepEqual(
        await ids(),
        index.slice(48, 96).map((r) => r.id),
      );
      const remote = index[1200];
      await page.locator("#catalog-search").fill(remote.title);
      assert((await ids()).some((id) => lookup.get(id).title === remote.title));
      assert.equal(new URL(page.url()).searchParams.get("page"), "1");
      await reset();
      await page.locator("#catalog-search").fill("tomato");
      assert((await ids()).length > 0);
      for (const id of await ids()) {
        const r = lookup.get(id);
        assert(
          [
            r.title,
            r.cuisine,
            r.meal_type,
            ...r.ingredients,
            ...r.proteins,
            ...r.methods,
          ]
            .join(" ")
            .toLowerCase()
            .includes("tomato"),
        );
      }
      await reset();
      for (const [key, field] of [
        ["cuisine", "cuisines"],
        ["meal_type", "meal_type"],
        ["protein", "proteins"],
        ["method", "methods"],
        ["time", "time_categories"],
      ]) {
        const choice = index.find((r) =>
          Array.isArray(r[field])
            ? r[field].some((v) => !["Other", "Unknown"].includes(v))
            : r[field] !== "Other",
        )[field];
        const value = Array.isArray(choice) ? choice[0] : choice;
        await filter(key).selectOption(value);
        await expected(
          index.filter((r) =>
            Array.isArray(r[field])
              ? r[field].includes(value)
              : r[field] === value,
          ),
        );
        await reset();
      }
      await filter("coverage").selectOption("85");
      await expected(
        index.filter((r) => r.coverage != null && r.coverage >= 0.85),
      );
      await reset();
      const sample = index.find(
        (r) =>
          r.cuisines[0] !== "Unknown" &&
          r.proteins[0] !== "Other" &&
          r.total_minutes > 0 &&
          r.total_minutes < 30,
      );
      await filter("cuisine").selectOption(sample.cuisines[0]);
      await filter("protein").selectOption(sample.proteins[0]);
      await filter("time").selectOption("Under 30 min");
      await expected(
        index.filter(
          (r) =>
            r.cuisines.includes(sample.cuisines[0]) &&
            r.proteins.includes(sample.proteins[0]) &&
            r.time_categories.includes("Under 30 min"),
        ),
      );
      const before = await ids();
      await page.locator(".card h2 a").first().click();
      assert.equal(
        await page.locator("h1").textContent(),
        lookup.get(before[0]).title,
      );
      assert(
        !/recommendation|\bscore\b|\branking\b|\d+\/100/i.test(
          await page.locator("body").innerText(),
        ),
      );
      const h = await page.locator("h2").allTextContents();
      assert(h.indexOf("Ingredients") < h.indexOf("Instructions"));
      assert(
        !/\b(tsp|tbsp|teaspoons?|tablespoons?)\b/i.test(
          (await page.locator(".ingredients,.steps").allTextContents()).join(
            " ",
          ),
        ),
      );
      await page.getByText("My kitchen notes", { exact: true }).click();
      await page.locator('[name="notes"]').fill("Browser verification");
      await page.locator('#personal-form button[type="submit"]').click();
      await page.reload();
      assert.equal(
        await page.locator('[name="notes"]').inputValue(),
        "Browser verification",
      );
      await page
        .getByRole("link", { name: "Back to recipes", exact: false })
        .click();
      await ready();
      assert.deepEqual(await ids(), before);
      assert.equal(await filter("cuisine").inputValue(), sample.cuisines[0]);
      await reset();
      for (const value of ["name", "time", "coverage"]) {
        await page.locator("#catalog-sort").selectOption(value);
        const rows = (await ids()).map((id) => lookup.get(id));
        for (let n = 1; n < rows.length; n++) {
          if (value === "name")
            assert(rows[n - 1].sort_title <= rows[n].sort_title);
          if (value === "time")
            assert(
              (rows[n - 1].total_minutes ?? Infinity) <=
                (rows[n].total_minutes ?? Infinity),
            );
          if (value === "coverage")
            assert((rows[n - 1].coverage ?? -1) >= (rows[n].coverage ?? -1));
        }
      }
      await page.locator("#catalog-sort").selectOption("time");
      await page
        .getByRole("button", {
          name: String(Math.ceil(index.length / 48)),
          exact: true,
        })
        .click();
      assert((await ids()).every((id) => lookup.get(id).total_minutes == null));
      await page.locator("#catalog-search").fill("zz-no-recipe-exists-zz");
      assert.equal((await ids()).length, 0);
      await reset();
      await expected(index);
      for (const path of ["index.html", index[0].url]) {
        await page.goto(base + path);
        if (path === "index.html") await ready();
        assert(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
          ),
        );
        await page.screenshot({
          path: `/tmp/menu-book-${viewport.width}-${path === "index.html" ? "catalog" : "detail"}.png`,
        });
      }
      assert.deepEqual(errors, []);
      checks.push({
        viewport,
        status: "passed",
        checks: [
          "full_catalog",
          "full_dataset_search",
          "six_filters",
          "combined_filters",
          "sorting",
          "unknown_time_last",
          "pagination",
          "stateful_back_link",
          "stable_recipe_links",
          "no_scores",
          "no_image_layout",
          "metric_units",
          "personal_notes",
          "no_overflow",
          "no_browser_errors",
        ],
      });
      await context.close();
    }
    // Static fallback exposes every page through ordinary previous/next links.
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto(base);
    assert.equal(await page.locator(".card").count(), 48);
    await page.getByRole("link", { name: "Next", exact: true }).click();
    assert(page.url().endsWith("page-2.html"));
    assert.equal(await page.locator(".card").count(), 48);
    await context.close();
    const report = {
      status: "passed",
      base_url: base,
      recipes: index.length,
      static_fallback: "passed",
      checks,
    };
    fs.writeFileSync(
      process.env.BROWSER_REPORT || "docs/catalog-browser-validation.json",
      JSON.stringify(report, null, 2) + "\n",
    );
    console.log(JSON.stringify(report));
  } finally {
    await browser?.close();
    server?.kill();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
