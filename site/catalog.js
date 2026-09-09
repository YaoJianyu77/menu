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
  function sourceLink(recipe) {
    const link = element(recipe.url ? "a" : "span", recipe.title);
    if (recipe.url) {
      link.href = recipe.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.title = recipe.title;
    }
    return link;
  }
  function recipeCard(recipe) {
    const card = element("article", undefined, "recipe-row");
    card.dataset.recipeId = recipe.id;
    const title = element("h2");
    const link = sourceLink(recipe);
    title.append(link);
    card.append(title);
    const facts = [];
    if (known(recipe.total_minutes) && recipe.total_minutes > 0)
      facts.push(`${recipe.total_minutes} min`);
    facts.push(
      ...recipe.methods
        .slice(0, 1)
        .filter((v) => !["Other", "Unknown"].includes(v)),
    );
    if (facts.length) card.append(element("p", facts.join(" · "), "row-meta"));
    const hide = element("button", "×", "hide-row");
    hide.type = "button";
    hide.dataset.hideId = recipe.id;
    hide.setAttribute("aria-label", `Hide ${recipe.title}`);
    hide.title = `Hide ${recipe.title}`;
    card.append(hide);
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
    const hiddenStore = window.recipeHidden;
    let hiddenIds = hiddenStore.read();
    const toggle = document.querySelector("#hidden-toggle");
    const panel = document.querySelector("#hidden-panel");
    const hiddenList = document.querySelector("#hidden-list");
    const toast = document.querySelector("#hidden-toast");
    const undo = document.querySelector("#hidden-undo");
    let undoId = null;
    let toastTimer;
    let page;
    function expireToast() {
      if (toast.contains(document.activeElement) || toast.matches(":hover")) {
        toastTimer = setTimeout(expireToast, 2000);
      } else toast.hidden = true;
    }
    function notify(id, saved = true) {
      undoId = id;
      document.querySelector("#hidden-message").textContent = saved
        ? "Recipe hidden."
        : "Recipe hidden for now. Browser storage could not save it.";
      toast.hidden = false;
      clearTimeout(toastTimer);
      toastTimer = setTimeout(expireToast, 10000);
    }
    function refresh() {
      hiddenIds = hiddenStore.read();
      render();
      renderHidden();
    }
    function renderHidden() {
      const hiddenRows = rows.filter((r) => hiddenIds.has(r.id));
      toggle.textContent = `Hidden (${hiddenRows.length.toLocaleString()})`;
      document.querySelector("#restore-all").disabled = hiddenRows.length === 0;
      if (panel.hidden) return;
      hiddenList.replaceChildren(
        ...hiddenRows.map((r) => {
          const li = element("li");
          const link = sourceLink(r);
          const restore = element("button", "Restore");
          restore.type = "button";
          restore.dataset.restoreId = r.id;
          restore.setAttribute("aria-label", `Restore ${r.title}`);
          li.append(link, restore);
          return li;
        }),
      );
      if (!hiddenRows.length)
        hiddenList.append(element("li", "No hidden recipes."));
    }
    toggle.hidden = false;
    toggle.addEventListener("click", () => {
      panel.hidden = !panel.hidden;
      toggle.setAttribute("aria-expanded", String(!panel.hidden));
      renderHidden();
    });
    function closePanel() {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      toggle.focus();
    }
    document
      .querySelector("#hidden-close")
      .addEventListener("click", closePanel);
    panel.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closePanel();
    });
    results.addEventListener("click", (event) => {
      const button = event.target.closest("[data-hide-id]");
      if (!button) return;
      const ordinal = [...results.querySelectorAll("[data-hide-id]")].indexOf(
        button,
      );
      const id = button.dataset.hideId;
      hiddenIds.add(id);
      const saved = hiddenStore.write(hiddenIds);
      render();
      renderHidden();
      notify(id, saved);
      const buttons = results.querySelectorAll("[data-hide-id]");
      (buttons[Math.min(ordinal, buttons.length - 1)] || toggle).focus({
        preventScroll: true,
      });
    });
    undo.addEventListener("click", () => {
      if (undoId) hiddenStore.restore(undoId);
      hiddenIds.delete(undoId);
      toast.hidden = true;
      clearTimeout(toastTimer);
      render();
      renderHidden();
      const row = [...results.querySelectorAll(".recipe-row")].find(
        (r) => r.dataset.recipeId === undoId,
      );
      (row?.querySelector("a") || toggle).focus({ preventScroll: true });
      undoId = null;
    });
    hiddenList.addEventListener("click", (event) => {
      const button = event.target.closest("[data-restore-id]");
      if (!button) return;
      hiddenStore.restore(button.dataset.restoreId);
      hiddenIds.delete(button.dataset.restoreId);
      render();
      renderHidden();
      (
        hiddenList.querySelector("button") ||
        document.querySelector("#hidden-close")
      ).focus({ preventScroll: true });
    });
    document.querySelector("#restore-all").addEventListener("click", () => {
      hiddenStore.write([]);
      hiddenIds.clear();
      render();
      renderHidden();
      document.querySelector("#hidden-close").focus();
    });
    window.addEventListener("storage", (e) => {
      if (e.key === hiddenStore.key || e.key === null) refresh();
    });
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
      if (hiddenIds.has(row.id)) return false;
      const terms = normalize(search.value.trim()).split(/\s+/).filter(Boolean);
      if (!terms.every((term) => row.searchText.includes(term))) return false;
      return filters.every((filter) => {
        if (!filter.value) return true;
        const key = filter.dataset.catalogFilter;
        const value = row[fields[key] || key];
        return Array.isArray(value)
          ? value.includes(filter.value)
          : value === filter.value;
      });
    }
    function order(a, b) {
      let difference = 0;
      if (sort.value === "time")
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
    renderHidden();
    configElement.dataset.loaded = "true";
  }
  start().catch(() =>
    count.after(
      element(
        "p",
        "Search is unavailable. All recipe titles remain available below.",
        "catalog-notice",
      ),
    ),
  );
})();
