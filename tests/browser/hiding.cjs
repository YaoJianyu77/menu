const assert = require("node:assert/strict");
module.exports = async function checkHiding(page, base, index) {
  const key = "my-recipes:hidden:v1";
  const ready = () =>
    page
      .locator('#catalog-config[data-loaded="true"]')
      .waitFor({ state: "attached" });
  const reload = async () => {
    await page.reload();
    await ready();
  };
  const count = () => page.locator("#catalog-count").textContent();
  const hide = (r) => page.locator(`[data-hide-id="${r.id}"]`).click();
  const has = (r) =>
    page.locator(`#catalog-results [data-recipe-id="${r.id}"]`).count();
  const read = () =>
    page.evaluate((key) => JSON.parse(localStorage.getItem(key) || "[]"), key);
  const allCount = `${index.length.toLocaleString()} recipes`;
  const r = index[0],
    second = index[1];
  assert.equal(
    await page.locator("#hidden-toggle").textContent(),
    "Hidden (0)",
  );
  assert.equal(
    await page.locator(`[data-hide-id="${r.id}"]`).getAttribute("aria-label"),
    `Hide ${r.title}`,
  );
  await hide(r);
  assert.equal(await has(r), 0);
  assert((await read()).includes(r.id));
  assert.equal(await count(), `${(index.length - 1).toLocaleString()} recipes`);
  assert(await page.locator("#hidden-toast").isVisible());
  await page.locator("#hidden-undo").focus();
  await page.keyboard.press("Enter");
  assert.equal(await has(r), 1);
  assert(!(await read()).includes(r.id));
  await hide(r);
  assert((await read()).includes(r.id));
  await reload();
  assert.equal(await has(r), 0);
  await page.locator("#catalog-search").fill(r.title);
  assert.equal(await has(r), 0);
  await page.locator("#catalog-reset").click();
  assert.equal(await has(r), 0);
  await page
    .locator('[data-catalog-filter="meal_type"]')
    .selectOption(r.meal_type);
  assert.equal(await has(r), 0);
  await page.locator("#catalog-reset").click();
  await page.locator("#hidden-toggle").click();
  assert(await page.locator(`[data-restore-id="${r.id}"]`).isVisible());
  assert.equal(
    await page.locator("#hidden-list a").first().textContent(),
    r.title,
  );
  await page.locator(`[data-restore-id="${r.id}"]`).click();
  assert.equal(await has(r), 1);
  await page.locator("#hidden-close").click();
  await hide(r);
  await hide(second);
  await page.locator("#hidden-undo").click();
  assert.equal(await has(second), 1);
  assert.equal(await has(r), 0);
  await hide(second);
  if (page.viewportSize().width === 1366) {
    await page
      .locator("#hidden-toast")
      .waitFor({ state: "hidden", timeout: 15000 });
  }
  await page.locator("#hidden-toggle").click();
  await page.locator("#restore-all").click();
  assert.equal(await count(), allCount);
  assert.deepEqual(await read(), []);
  await page.locator("#hidden-close").click();
  // Removing the sole item from the final page clamps pagination to page 1.
  await page.evaluate(
    ({ key, ids }) => localStorage.setItem(key, JSON.stringify(ids)),
    { key, ids: index.slice(121).map((r) => r.id) },
  );
  await page.goto(base + "index.html?page=2");
  await ready();
  assert.equal(await page.locator("#catalog-results .recipe-row").count(), 1);
  await hide(index[120]);
  assert.equal(new URL(page.url()).searchParams.get("page"), "1");
  assert.equal(await page.locator("#catalog-results .recipe-row").count(), 120);
  await page.locator("#hidden-toggle").click();
  await page.locator("#restore-all").click();
  await page.locator("#hidden-close").click();
  // Every record remains restorable even when the visible catalog is empty.
  await page.evaluate(
    ({ key, ids }) => localStorage.setItem(key, JSON.stringify(ids)),
    { key, ids: index.map((r) => r.id) },
  );
  await reload();
  assert.equal(await count(), "0 recipes");
  await page.locator("#hidden-toggle").click();
  await page.locator("#restore-all").click();
  assert.equal(await count(), allCount);
  await page.locator("#hidden-close").click();
  for (const raw of ["{broken", '{"bad":true}', '["old-missing-id",null,3]']) {
    await page.evaluate(({ key, raw }) => localStorage.setItem(key, raw), {
      key,
      raw,
    });
    await reload();
    assert.equal(await count(), allCount);
    assert.equal(
      await page.locator("#hidden-toggle").textContent(),
      "Hidden (0)",
    );
  }
  await page.evaluate((key) => localStorage.removeItem(key), key);
  await reload();
  // Hide controls remain distinct accessible tap targets on mobile.
  const box = await page.locator(`[data-hide-id="${r.id}"]`).boundingBox();
  assert(box.width >= 28 && box.height >= 28);
};
