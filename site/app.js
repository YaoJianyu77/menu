/* Personal notes stay in this browser. */
(() => {
  const back = document.querySelector("[data-back-to-recipes]");
  try {
    const query = sessionStorage.getItem("my-recipes-catalog-query");
    if (back && query?.startsWith("?")) back.href += query;
  } catch {
    /* A plain homepage link remains available. */
  }
  document.querySelectorAll("figure img").forEach((img) => {
    const remove = () => img.closest("figure")?.remove();
    img.addEventListener("error", remove);
    if (img.complete && !img.naturalWidth) remove();
  });
  const payload = document.querySelector("#recipe-data");
  if (!payload) return;
  const recipe = JSON.parse(payload.textContent);
  const hide = document.querySelector("#hide-recipe");
  if (hide && window.recipeHidden) {
    hide.hidden = false;
    hide.addEventListener("click", () => {
      if (!window.recipeHidden.hide(recipe.id)) {
        document.querySelector("#hide-error").textContent =
          "Could not save hidden recipes. Allow browser storage to keep this preference.";
        return;
      }
      try {
        sessionStorage.setItem("my-recipes:hidden-undo", recipe.id);
      } catch {
        /* Hiding still persists. */
      }
      location.assign(back.href);
    });
  }
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
