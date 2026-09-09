const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
function setup(raw = null, blocked = false) {
  const context = {
    window: {},
    localStorage: {
      getItem() {
        if (blocked) throw Error("Denied");
        return raw;
      },
      setItem(key, value) {
        if (blocked) throw Error("Denied");
        raw = value;
      },
    },
  };
  vm.runInNewContext(fs.readFileSync("site/hidden.js", "utf8"), context);
  return {
    store: context.window.recipeHidden,
    raw: () => raw,
    corrupt: () => {
      raw = "{bad";
    },
  };
}
test("stable IDs persist independently of titles; undo and restore are idempotent", () => {
  const { store, raw } = setup();
  assert(store.hide("id-a"));
  assert(store.hide("id-a"));
  assert(store.hide("id-b"));
  assert.deepEqual(JSON.parse(raw()), ["id-a", "id-b"]);
  assert.deepEqual([...setup(raw()).store.read()], ["id-a", "id-b"]);
  assert(store.restore("id-a"));
  assert(store.restore("id-a"));
  assert.deepEqual(JSON.parse(raw()), ["id-b"]);
  store.write([]);
  assert.deepEqual(JSON.parse(raw()), []);
});
for (const raw of ["{broken", '"wrong"', "null", '{"ids": []}', "123"]) {
  test(`invalid data safely ignored: ${raw}`, () =>
    assert.equal(setup(raw).store.read().size, 0));
}
test("mixed and unknown IDs are safe, deduplicated, and preserved", () => {
  const { store } = setup(
    '["old-id", "valid-id", 123, null, {}, "", "valid-id"]',
  );
  assert.deepEqual([...store.read()], ["old-id", "valid-id"]);
});
test("corruption after a valid read does not retain stale preferences", () => {
  const t = setup('["a"]');
  t.store.read();
  t.corrupt();
  assert.equal(t.store.read().size, 0);
});
test("blocked storage returns failure and keeps a usable in-memory preference", () => {
  const { store } = setup(null, true);
  assert.equal(store.hide("a"), false);
  assert.deepEqual([...store.read()], ["a"]);
  store.restore("a");
  assert.equal(store.read().size, 0);
});
