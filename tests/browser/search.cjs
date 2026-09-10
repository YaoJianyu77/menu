const assert = require("node:assert/strict");
require("../../site/search.js");
const ingredient = (canonical, terms = []) => ({
  canonical,
  terms,
  aliases: terms,
});
const row = (id, title, ingredients, extra = {}) => ({
  id,
  title,
  ingredient_search: ingredients,
  ...extra,
});
const rows = [
  row("both", "Dinner skillet", [
    ingredient("chicken breast", ["boneless skinless chicken breasts"]),
    ingredient("mushroom", ["mushrooms"]),
  ]),
  row("single", "Another dinner", [ingredient("chicken breast")]),
  row("meta", "Plain dinner", [], { cuisine: "Mushroom" }),
  row("alias", "Green dinner", [
    ingredient("green onion", ["scallion", "scallions", "spring onion"]),
    ingredient("egg", ["eggs"]),
    ingredient("tomato", ["tomatoes", "roma tomatoes"]),
  ]),
  row("original", "红烧肉", [], { original_title: "红烧肉做法" }),
  row("potato", "Spuds", [ingredient("potato", ["potatoes"])]),
  row("stew", "Stew", [ingredient("beef"), ingredient("baby red potatoes")]),
  row("raw", "Cheese plate", [
    ingredient("cheese", ["100 g burrata torn into pieces"]),
  ]),
  row("exact", "Mushroom", []),
  row("prefix", "Mushroom rice", []),
];
const engine = recipeSearch.prepare(rows);
function search(q) {
  const query = engine.query(q);
  return rows
    .map((r) => ({ r, s: engine.evaluate(r, query) }))
    .filter((x) => x.s.eligible)
    .sort(
      (a, b) =>
        a.s.priority - b.s.priority ||
        b.s.ingredients - a.s.ingredients ||
        a.r.position - b.r.position,
    )
    .map((x) => x.r.id);
}
assert.deepEqual(search("chicken mushroom"), ["both"]);
assert.deepEqual(search("mushroom chicken"), ["both"]);
assert.deepEqual(search("mushroom"), ["exact", "prefix", "both", "meta"]);
for (const q of [
  "green onion",
  "scallion",
  "scallions",
  "spring onion",
  "egg",
  "eggs",
  "tomato",
  "tomatoes",
  "roma tomatoes",
  "egg tomato",
])
  assert.deepEqual(search(q), ["alias"], q);
assert.deepEqual(search("mushrooms"), ["both"]);
assert.deepEqual(search("chicken breast"), ["both", "single"]);
assert.deepEqual(search("burrata"), ["raw"]);
assert.deepEqual(search("红烧肉做法"), ["original"]);
assert.deepEqual(search("nothing"), []);
assert.equal(search("").length, rows.length);
assert.deepEqual(search("chicken mushroom"), search("CHICKEN   MUSHROOM"));
console.log(
  "Ingredient aliases, original text, AND matching, relevance and deterministic search passed.",
);

assert.deepEqual(search("beef potato"), ["stew"]);
