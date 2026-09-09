/* Browser-local preferences shared by the directory and recipe detail pages. */
(() => {
  const key = "my-recipes:hidden:v1";
  let memory = new Set();
  const valid = (ids) =>
    new Set(
      Array.isArray(ids)
        ? ids.filter((id) => typeof id === "string" && id.length > 0)
        : [],
    );
  window.recipeHidden = {
    key,
    read() {
      let raw;
      try {
        raw = localStorage.getItem(key);
      } catch {
        return new Set(memory);
      }
      try {
        memory = valid(JSON.parse(raw || "[]"));
      } catch {
        memory = new Set();
      }
      return new Set(memory);
    },
    write(ids) {
      memory = valid([...ids]);
      try {
        localStorage.setItem(key, JSON.stringify([...memory].sort()));
        return true;
      } catch {
        return false;
      }
    },
    hide(id) {
      const ids = this.read();
      ids.add(id);
      return this.write(ids);
    },
    restore(id) {
      const ids = this.read();
      ids.delete(id);
      return this.write(ids);
    },
  };
})();
