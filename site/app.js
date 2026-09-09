/* All interaction is local; this website makes no network requests. */
(() => {
  const cards = [...document.querySelectorAll(".card")];
  const filters = [...document.querySelectorAll("[data-filter]")];
  for (const select of filters.filter((el) => el.tagName === "SELECT")) {
    const values = new Set(
      cards
        .flatMap((card) =>
          (card.dataset[select.dataset.filter] || "").split("|"),
        )
        .filter(Boolean),
    );
    for (const value of [...values].sort())
      select.add(new Option(value, value));
  }
  const search = document.querySelector("#search");
  function filter() {
    let count = 0;
    for (const card of cards) {
      const visible =
        card.dataset.name.toLowerCase().includes(search.value.toLowerCase()) &&
        filters.every((input) => {
          if (!input.value) return true;
          const key = input.dataset.filter;
          const value = card.dataset[key];
          if (["total", "active", "coverage"].includes(key)) {
            if (value === "") return false;
            return key === "coverage"
              ? Number(value) * 100 >= Number(input.value)
              : Number(value) <= Number(input.value);
          }
          return value.split("|").includes(input.value);
        });
      card.hidden = !visible;
      count += Number(visible);
    }
    document.querySelector("#count").textContent = `${count} recipes`;
    document.querySelector("#empty").hidden = count > 0;
  }
  if (search) {
    [search, ...filters].forEach((input) =>
      input.addEventListener("input", filter),
    );
    document.querySelector("#reset").addEventListener("click", () => {
      [search, ...filters].forEach((input) => {
        input.value = "";
      });
      filter();
    });
  }
  const payload = document.querySelector("#recipe-data");
  if (!payload) return;
  const recipe = JSON.parse(payload.textContent);
  const form = document.querySelector("#personal-form");
  const status = document.querySelector("#save-status");
  const storageKey = "everyday-recipes-annotations-v1";
  function readNotes() {
    return JSON.parse(localStorage.getItem(storageKey) || "{}");
  }
  function fill(notes) {
    for (const field of form.elements) {
      if (!field.name) continue;
      if (field.type === "checkbox") field.checked = notes[field.name] === true;
      else field.value = notes[field.name] ?? "";
    }
  }
  try {
    fill({ ...recipe.personal, ...readNotes()[recipe.id] });
  } catch {
    fill(recipe.personal);
    status.textContent =
      "Browser storage is unavailable. Export your notes before leaving.";
  }
  function values() {
    return Object.fromEntries(
      [...form.elements]
        .filter((f) => f.name)
        .map((f) => [f.name, f.type === "checkbox" ? f.checked : f.value]),
    );
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      localStorage.setItem(
        storageKey,
        JSON.stringify({ ...readNotes(), [recipe.id]: values() }),
      );
      status.textContent = "Saved in this browser.";
    } catch {
      status.textContent = "Could not save in this browser. Export your notes.";
    }
  });
  document.querySelector("#export-notes").addEventListener("click", () => {
    let notes = {};
    try {
      notes = readNotes();
    } catch {
      /* Export still includes current fields. */
    }
    notes[recipe.id] = values();
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(notes, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "recipe-notes.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  document
    .querySelector("#import-notes")
    .addEventListener("change", async (event) => {
      try {
        const data = JSON.parse(await event.target.files[0].text());
        if (
          !data ||
          Array.isArray(data) ||
          typeof data !== "object" ||
          Object.values(data).some(
            (value) =>
              !value || Array.isArray(value) || typeof value !== "object",
          )
        )
          throw Error("Expected recipe IDs mapped to notes.");
        const merged = { ...readNotes(), ...data };
        localStorage.setItem(storageKey, JSON.stringify(merged));
        fill({ ...recipe.personal, ...merged[recipe.id] });
        status.textContent = "Notes imported.";
      } catch {
        status.textContent =
          "Import failed. Use a recipe notes JSON export and enable browser storage.";
      }
    });
})();
