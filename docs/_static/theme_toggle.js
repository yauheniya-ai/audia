/* audia docs — dark/light theme toggle
   Dark mode is default; preference persisted in localStorage.
   The button is injected into the page once the DOM is ready.
*/
(function () {
  const STORAGE_KEY = "audia-theme";
  const LIGHT_CLASS = "light-mode";
  const DARK_LABEL  = "☀ light";
  const LIGHT_LABEL = "☽ dark";

  function applyTheme(isLight) {
    if (isLight) {
      document.body.classList.add(LIGHT_CLASS);
    } else {
      document.body.classList.remove(LIGHT_CLASS);
    }
    const btn = document.getElementById("audia-theme-toggle");
    if (btn) btn.textContent = isLight ? LIGHT_LABEL : DARK_LABEL;
  }

  function createButton() {
    const btn = document.createElement("button");
    btn.id = "audia-theme-toggle";
    btn.setAttribute("aria-label", "Toggle light/dark theme");
    btn.textContent = DARK_LABEL;
    btn.addEventListener("click", function () {
      const nowLight = !document.body.classList.contains(LIGHT_CLASS);
      localStorage.setItem(STORAGE_KEY, nowLight ? "light" : "dark");
      applyTheme(nowLight);
    });
    document.body.appendChild(btn);
  }

  function init() {
    // Default is dark; switch to light only if explicitly saved
    const saved = localStorage.getItem(STORAGE_KEY);
    const isLight = saved === "light";
    applyTheme(isLight);
    createButton();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
