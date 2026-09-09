/* One complete local catalog; filters and pagination are encoded in the URL. */
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
  const fields = {
    cuisine: "cuisines",
    protein: "proteins",
    method: "methods",
    time: "time_categories",
  };
  const normalize = (v) =>
    String(v ?? "")
      .normalize("NFKC")
      .toLowerCase();
  const known = (v) => typeof v === "number" && Number.isFinite(v);
  const element = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  function recipeCard(recipe) {
    const card = element("article", undefined, "card recipe-card");
    card.dataset.recipeId = recipe.id;
    const title = element("h2");
    const link = element("a", recipe.title);
    link.href = recipe.url;
    title.append(link);
    card.append(title);
    if (recipe.image && /^https?:\/\//i.test(recipe.image.url)) {
      const figure = element("figure", undefined, "card-image");
      const img = element("img");
      img.src = recipe.image.url;
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.referrerPolicy = "no-referrer";
      img.addEventListener("error", () => figure.remove());
      figure.append(img);
      if (recipe.image.attribution)
        figure.append(element("figcaption", recipe.image.attribution));
      card.append(figure);
    }
    const labels = [
      ...recipe.cuisines.filter((v) => v !== "Unknown"),
      recipe.meal_type,
    ];
    card.append(element("p", labels.join(" · "), "card-category"));
    const facts = [];
    if (known(recipe.total_minutes)) facts.push(`${recipe.total_minutes} min`);
    facts.push(...recipe.methods.filter((v) => v !== "Other"));
    card.append(element("p", facts.join(" · "), "card-meta"));
    card.append(
      element(
        "p",
        known(recipe.coverage)
          ? `Food Lion ${Math.round(recipe.coverage * 100)}%`
          : "Food Lion Unknown",
        "card-meta",
      ),
    );
    return card;
  }
  async function start() {
    const response = await fetch(config.index_url);
    if (!response.ok) throw Error("Catalog index unavailable");
    const rows = await response.json();
    rows.forEach((row, position) => {
      row.position = position;
      row.searchText = normalize(
        [
          row.title,
          row.cuisine,
          row.meal_type,
          ...row.ingredients,
          ...row.proteins,
          ...row.methods,
        ].join(" "),
      );
    });
    let page;
    function restore() {
      const params = new URLSearchParams(location.search);
      search.value = params.get("q") || "";
      filters.forEach((f) => {
        f.value = params.get(f.dataset.catalogFilter) || "";
      });
      sort.value = params.get("sort") || "default";
      if (!sort.value) sort.value = "default";
      const candidate = Number(params.get("page") || config.initial_page || 1);
      page = Number.isSafeInteger(candidate) && candidate > 0 ? candidate : 1;
    }
    function matches(row) {
      const terms = normalize(search.value.trim()).split(/\s+/).filter(Boolean);
      if (!terms.every((term) => row.searchText.includes(term))) return false;
      return filters.every((filter) => {
        if (!filter.value) return true;
        const key = filter.dataset.catalogFilter;
        if (key === "coverage")
          return (
            known(row.coverage) && row.coverage * 100 >= Number(filter.value)
          );
        const value = row[fields[key] || key];
        return Array.isArray(value)
          ? value.includes(filter.value)
          : value === filter.value;
      });
    }
    function order(a, b) {
      let difference = 0;
      if (sort.value === "coverage")
        difference = (b.coverage ?? -1) - (a.coverage ?? -1);
      else if (sort.value === "time")
        difference =
          (a.total_minutes ?? Infinity) - (b.total_minutes ?? Infinity);
      else if (sort.value === "default") difference = a.position - b.position;
      if (difference && !Number.isNaN(difference)) return difference;
      return (
        (a.sort_title < b.sort_title
          ? -1
          : a.sort_title > b.sort_title
            ? 1
            : 0) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
      );
    }
    function remember() {
      const params = new URLSearchParams();
      if (search.value) params.set("q", search.value);
      for (const f of filters)
        if (f.value) params.set(f.dataset.catalogFilter, f.value);
      if (sort.value !== "default") params.set("sort", sort.value);
      // Explicit page also overrides a static page-N fallback when filters reset.
      params.set("page", page);
      const query = `?${params}`;
      history.replaceState(null, "", query);
      try {
        sessionStorage.setItem("my-recipes-catalog-query", query);
      } catch {
        /* URL still preserves state. */
      }
    }
    function render() {
      const matching = rows.filter(matches).sort(order);
      const pages = Math.max(1, Math.ceil(matching.length / config.page_size));
      page = Math.min(page, pages);
      const start = (page - 1) * config.page_size;
      results.replaceChildren(
        ...matching.slice(start, start + config.page_size).map(recipeCard),
      );
      if (!matching.length)
        results.append(
          element(
            "p",
            "No recipes match these filters. Try a broader search.",
            "catalog-empty",
          ),
        );
      count.textContent = `${matching.length.toLocaleString()} recipes`;
      pagination.replaceChildren();
      if (pages > 1) {
        function button(label, target, disabled = false) {
          const b = element("button", label);
          b.type = "button";
          b.disabled = disabled;
          if (String(target) === label && target === page)
            b.setAttribute("aria-current", "page");
          b.addEventListener("click", () => {
            page = target;
            render();
            count.focus({ preventScroll: true });
            results.scrollIntoView({ block: "start" });
          });
          pagination.append(b);
        }
        button("Previous", page - 1, page === 1);
        const shown = new Set([1, pages]);
        for (let n = Math.max(1, page - 2); n <= Math.min(pages, page + 2); n++)
          shown.add(n);
        let previous = 0;
        for (const n of [...shown].sort((a, b) => a - b)) {
          if (previous && n > previous + 1)
            pagination.append(element("span", "…"));
          button(String(n), n);
          previous = n;
        }
        button("Next", page + 1, page === pages);
      }
      remember();
    }
    count.tabIndex = -1;
    for (const input of [search, sort, ...filters])
      input.addEventListener("input", () => {
        page = 1;
        render();
      });
    document.querySelector("#catalog-reset").addEventListener("click", () => {
      search.value = "";
      filters.forEach((f) => {
        f.value = "";
      });
      sort.value = "default";
      page = 1;
      render();
    });
    window.addEventListener("popstate", () => {
      restore();
      render();
    });
    restore();
    render();
    configElement.dataset.loaded = "true";
  }
  start().catch(() =>
    count.after(
      element(
        "p",
        "Search is unavailable. You can still browse using the page links below.",
        "catalog-notice",
      ),
    ),
  );
})();
