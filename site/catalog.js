/* Static catalog: one local index, compact pages, no third-party service. */
(() => {
  const configElement = document.querySelector("#catalog-config");
  if (!configElement) return;
  const config = JSON.parse(configElement.textContent);
  const results = document.querySelector("#catalog-results");
  const count = document.querySelector("#catalog-count");
  const pagination = document.querySelector("#catalog-pagination");
  const search = document.querySelector("#catalog-search");
  const filters = [...document.querySelectorAll("[data-catalog-filter]")];
  const sort = document.querySelector("#catalog-sort");
  const pageSize = config.page_size || 48;
  const fields = {
    cuisine: "cuisines",
    protein: "proteins",
    method: "methods",
    time: "time_categories",
  };
  const normalize = (value) =>
    String(value ?? "")
      .normalize("NFKC")
      .toLowerCase();
  const values = (row, key) => {
    const value = row[fields[key] || key];
    return Array.isArray(value) ? value : [value];
  };
  const knownNumber = (value) =>
    typeof value === "number" && Number.isFinite(value);
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const rootUrl = (path) => `${config.base_url || ""}${path}`;

  function recipeCard(recipe) {
    const card = element("article", undefined, "card recipe-card");
    card.dataset.recipeId = recipe.id;
    if (recipe.image && /^https?:\/\//i.test(recipe.image.url)) {
      const figure = element("figure", undefined, "card-image");
      const img = element("img");
      img.src = recipe.image.url;
      img.alt = recipe.title;
      img.loading = "lazy";
      img.decoding = "async";
      img.referrerPolicy = "no-referrer";
      img.addEventListener("error", () => figure.remove());
      figure.append(img);
      if (recipe.image.attribution) {
        const caption = element("figcaption", recipe.image.attribution);
        figure.append(caption);
      }
      card.append(figure);
    }
    const title = element("h2");
    const link = element("a", recipe.title);
    link.href = rootUrl(recipe.url);
    title.append(link);
    card.append(title);
    card.append(
      element(
        "p",
        `${recipe.cuisine || "Unknown"} · ${recipe.meal_type || "Other"}`,
        "card-category",
      ),
    );
    const facts = [];
    if (knownNumber(recipe.total_minutes))
      facts.push(`${recipe.total_minutes} min`);
    if (recipe.effort_level) facts.push(recipe.effort_level);
    if (recipe.methods?.length) facts.push(recipe.methods.join(" / "));
    if (facts.length) card.append(element("p", facts.join(" · "), "card-meta"));
    const stats = element("p", undefined, "card-stats");
    stats.append(
      element(
        "span",
        knownNumber(recipe.coverage)
          ? `Food Lion ${Math.round(recipe.coverage * 100)}%`
          : "Food Lion: Unknown",
      ),
    );
    stats.append(
      element(
        "strong",
        knownNumber(recipe.score)
          ? `Score ${Number(recipe.score.toFixed(1))}`
          : "Score unknown",
      ),
    );
    card.append(stats);
    return card;
  }

  function inScope(row) {
    const scope = config.scope || {};
    if (scope.axis && !values(row, scope.axis).includes(scope.value))
      return false;
    if (
      scope.recommended &&
      (!row.everyday_eligible || row.discovery_representative === false)
    )
      return false;
    if (scope.score_min != null && row.score < scope.score_min) return false;
    if (scope.score_max != null && row.score > scope.score_max) return false;
    if (scope.easy && row.effort_level !== "Easy") return false;
    if (
      scope.max_time != null &&
      (!knownNumber(row.total_minutes) || row.total_minutes > scope.max_time)
    )
      return false;
    if (
      scope.minimum_coverage != null &&
      (!knownNumber(row.coverage) || row.coverage < scope.minimum_coverage)
    )
      return false;
    return true;
  }

  async function start() {
    const response = await fetch(config.index_url);
    if (!response.ok) throw Error("Catalog index unavailable");
    const payload = await response.json();
    const rows = (Array.isArray(payload) ? payload : payload.recipes).filter(
      inScope,
    );
    for (const row of rows) {
      row.searchText = normalize(
        [
          row.title,
          row.cuisine,
          row.meal_type,
          ...(row.ingredients || []),
          ...(row.proteins || []),
          ...(row.methods || []),
        ].join(" "),
      );
    }
    for (const filter of filters.filter((item) => item.tagName === "SELECT")) {
      if (
        !["cuisine", "meal_type", "protein", "method"].includes(
          filter.dataset.catalogFilter,
        )
      )
        continue;
      const existing = new Set(
        [...filter.options].map((option) => option.value),
      );
      const choices = [
        ...new Set(
          rows
            .flatMap((row) => values(row, filter.dataset.catalogFilter))
            .filter(Boolean),
        ),
      ].sort();
      for (const choice of choices)
        if (!existing.has(choice)) filter.add(new Option(choice, choice));
    }
    let page = Math.max(1, Number(config.initial_page) || 1);
    function matches(row) {
      const terms = normalize(search?.value.trim())
        .split(/\s+/)
        .filter(Boolean);
      if (!terms.every((term) => row.searchText.includes(term))) return false;
      return filters.every((filter) => {
        if (filter.value === "") return true;
        const key = filter.dataset.catalogFilter;
        if (key === "min-score") return row.score >= Number(filter.value);
        if (key === "max-score") return row.score <= Number(filter.value);
        if (key === "coverage")
          return (
            knownNumber(row.coverage) &&
            row.coverage * 100 >= Number(filter.value)
          );
        if (key === "total")
          return (
            knownNumber(row.total_minutes) &&
            row.total_minutes <= Number(filter.value)
          );
        return values(row, key).includes(filter.value);
      });
    }
    function order(a, b) {
      let difference = 0;
      if (sort?.value === "coverage")
        difference = (b.coverage ?? -1) - (a.coverage ?? -1);
      else if (sort?.value === "time")
        difference =
          (a.total_minutes ?? Infinity) - (b.total_minutes ?? Infinity);
      else if (sort?.value !== "name")
        difference =
          knownNumber(a.rank) && knownNumber(b.rank)
            ? a.rank - b.rank
            : b.score - a.score;
      if (difference && !Number.isNaN(difference)) return difference;
      const left = a.sort_title ?? normalize(a.title),
        right = b.sort_title ?? normalize(b.title);
      return (
        (left < right ? -1 : left > right ? 1 : 0) ||
        (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
      );
    }
    function render() {
      const matching = rows.filter(matches).sort(order);
      const pages = Math.max(1, Math.ceil(matching.length / pageSize));
      page = Math.min(page, pages);
      const start = (page - 1) * pageSize;
      results.replaceChildren(
        ...matching.slice(start, start + pageSize).map(recipeCard),
      );
      if (!matching.length)
        results.append(
          element(
            "p",
            "No recipes match these filters. Try a broader search.",
            "catalog-empty",
          ),
        );
      count.textContent = `${matching.length.toLocaleString()} recipes${matching.length ? ` · Showing ${start + 1}–${Math.min(start + pageSize, matching.length)}` : ""}`;
      pagination.replaceChildren();
      if (pages > 1) {
        const previous = element("button", "Previous");
        previous.type = "button";
        previous.disabled = page === 1;
        const next = element("button", "Next");
        next.type = "button";
        next.disabled = page === pages;
        function navigate(change) {
          page += change;
          render();
          results.scrollIntoView({ block: "start" });
          count.focus({ preventScroll: true });
        }
        previous.addEventListener("click", () => navigate(-1));
        next.addEventListener("click", () => navigate(1));
        pagination.append(
          previous,
          element("span", `Page ${page} of ${pages}`),
          next,
        );
      }
    }
    count.setAttribute("tabindex", "-1");
    count.setAttribute("aria-live", "polite");
    for (const input of [search, sort, ...filters].filter(Boolean))
      input.addEventListener("input", () => {
        page = 1;
        render();
      });
    document.querySelector("#catalog-reset")?.addEventListener("click", () => {
      for (const filter of filters) filter.value = "";
      if (search) search.value = "";
      if (sort) sort.value = "score";
      page = 1;
      render();
    });
    render();
    configElement.dataset.loaded = "true";
  }
  start().catch(() => {
    const message = element(
      "p",
      "Search is unavailable. You can still browse using the page links below.",
      "catalog-notice",
    );
    count.after(message);
  });
})();
