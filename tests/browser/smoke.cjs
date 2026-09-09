/* Optional real-browser verification: PLAYWRIGHT_MODULE points to an installed playwright module. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1366, height: 900 },
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("http://127.0.0.1:8000/", { waitUntil: "networkidle" });
  const count = await page.locator(".card").count();
  if (count < 2) throw Error("Expected collected recipe cards");
  await page.locator("#search").fill("zzzz-no-recipe-matches-zzzz");
  if ((await page.locator(".card:visible").count()) !== 0)
    throw Error("Search filter failed");
  await page.locator("#reset").click();
  await page.locator('[data-filter="coverage"]').fill("100");
  if ((await page.locator(".card:visible").count()) !== 0)
    throw Error("Unverified inventory filter failed");
  await page.locator("#reset").click();
  const urls = await page
    .locator(".card h2 a")
    .evaluateAll((links) => links.slice(0, 3).map((link) => link.href));
  for (const url of urls) {
    await page.goto(url);
    if (!(await page.locator("h1").textContent()))
      throw Error("Missing recipe title");
    if ((await page.locator(".ingredients li").count()) < 1)
      throw Error("Missing ingredients");
    await page.locator('[name="notes"]').fill("Browser smoke test note");
    await page.locator('[name="cooked"]').check();
    await page.locator('button[type="submit"]').click();
    await page.reload();
    if (
      (await page.locator('[name="notes"]').inputValue()) !==
      "Browser smoke test note"
    )
      throw Error("Notes did not persist");
    if (!(await page.locator('[name="cooked"]').isChecked()))
      throw Error("Cooked state did not persist");
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("http://127.0.0.1:8000/");
  if (
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth + 1,
    )
  )
    throw Error("Mobile overflow");
  await page.screenshot({ path: "/tmp/menu-mobile.png", fullPage: false });
  await page.goto(urls[0]);
  if (
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth + 1,
    )
  )
    throw Error("Recipe mobile overflow");
  await page.screenshot({ path: "/tmp/menu-recipe.png", fullPage: false });
  if (errors.length) throw Error(errors.join("\n"));
  console.log(
    JSON.stringify({
      cards: count,
      recipePages: urls.length,
      search: "passed",
      coverageFilter: "passed",
      notes: "passed",
      mobile: "passed",
      browserErrors: errors,
    }),
  );
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
