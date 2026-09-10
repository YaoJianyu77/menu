/* Preserve the last catalog query without changing recipe identity or data. */
(() => {
  const back = document.querySelector("[data-back-to-recipes]");
  if (!back) return;
  try {
    const query = sessionStorage.getItem("my-recipes-catalog-query");
    if (query?.startsWith("?")) back.href += query;
  } catch {
    /* Plain back link works without storage. */
  }
})();
