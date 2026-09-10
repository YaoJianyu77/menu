/* Deterministic ingredient-aware search; vocabulary is generated from existing aliases. */
(() => {
  const text = (value) =>
    String(value ?? "")
      .normalize("NFKC")
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, " ")
      .trim()
      .replace(/\s+/g, " ");
  const contains = (haystack, needle) =>
    (" " + haystack + " ").includes(" " + needle + " ");
  function prepare(rows) {
    const aliases = new Map();
    const variants = new Map();
    rows.forEach((row, position) => {
      row.position = position;
      row.titleText = text(row.title);
      row.originalTitleText = text(row.original_title);
      row.ingredientTexts = (row.ingredient_search || []).map((item) => {
        const canonical = text(item.canonical);
        const terms = (item.terms || []).map(text).filter(Boolean);
        if (canonical) {
          if (!variants.has(canonical))
            variants.set(canonical, new Set([canonical]));
          for (const alias of (item.aliases || []).map(text).filter(Boolean))
            variants.get(canonical).add(alias);
        }
        // Persisted terms include original ingredient lines as well as curated aliases.
        for (const term of [canonical, ...terms]) {
          if (!term || !canonical) continue;
          if (!aliases.has(term)) aliases.set(term, new Set());
          aliases.get(term).add(canonical);
        }
        return { canonical, terms };
      });
      row.metadataText = text(
        [
          row.title,
          row.original_title,
          row.cuisine,
          row.meal_type,
          ...(row.proteins || []),
          ...(row.methods || []),
          ...(row.ingredients || []),
        ].join(" "),
      );
    });
    return {
      query(value) {
        const normalized = text(value),
          words = normalized.split(" ").filter(Boolean),
          parts = [];
        for (let i = 0; i < words.length; ) {
          let length = 1,
            phrase = words[i];
          for (let n = Math.min(8, words.length - i); n > 1; n--) {
            const candidate = words.slice(i, i + n).join(" ");
            if (aliases.has(candidate)) {
              phrase = candidate;
              length = n;
              break;
            }
          }
          const canonical = aliases.get(phrase) || new Set();
          const phrases = new Set([phrase]);
          for (const name of canonical)
            for (const variant of variants.get(name) || [])
              phrases.add(variant);
          parts.push({ phrase, canonical, phrases });
          i += length;
        }
        return { normalized, parts };
      },
      evaluate(row, query) {
        if (!query.normalized)
          return { eligible: true, priority: 0, ingredients: 0 };
        let ingredients = 0,
          all = true;
        for (const part of query.parts) {
          const match = row.ingredientTexts.some(
            (item) =>
              part.canonical.has(item.canonical) ||
              contains(item.canonical, part.phrase) ||
              [item.canonical, ...item.terms].some((term) =>
                [...part.phrases].some((phrase) => contains(term, phrase)),
              ),
          );
          if (match) ingredients++;
          if (!match && !contains(row.metadataText, part.phrase)) all = false;
        }
        const exact = [row.titleText, row.originalTitleText].includes(
          query.normalized,
        );
        const strong = [row.titleText, row.originalTitleText].some(
          (t) =>
            t.startsWith(query.normalized) || contains(t, query.normalized),
        );
        // AND eligibility prevents unrelated partial matches; every query part must be evidenced.
        return {
          eligible: all || exact || strong,
          priority: exact
            ? 0
            : strong
              ? 1
              : ingredients === query.parts.length
                ? 2
                : ingredients
                  ? 3
                  : 4,
          ingredients,
        };
      },
    };
  }
  globalThis.recipeSearch = { prepare };
})();
