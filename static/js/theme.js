/**
 * Theme manager — persists light/dark preference in localStorage
 * and applies it before first paint to prevent flash.
 *
 * Include in <head> without defer/async.
 * Call Theme.toggle() from the toggle button.
 */
(function () {
  const STORAGE_KEY = "crm-theme";
  const DARK_CLASS = "dark";

  const Theme = {
    init() {
      const stored = localStorage.getItem(STORAGE_KEY);
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      const isDark = stored ? stored === "dark" : prefersDark;
      document.documentElement.classList.toggle(DARK_CLASS, isDark);
      this._updateIcon(isDark);
    },

    toggle() {
      const isDark = document.documentElement.classList.toggle(DARK_CLASS);
      localStorage.setItem(STORAGE_KEY, isDark ? "dark" : "light");
      this._updateIcon(isDark);
    },

    current() {
      return document.documentElement.classList.contains(DARK_CLASS) ? "dark" : "light";
    },

    _updateIcon(isDark) {
      const btn = document.getElementById("theme-toggle");
      if (!btn) return;
      btn.setAttribute("aria-label", isDark ? "Switch to light mode" : "Switch to dark mode");
      const icon = btn.querySelector("[data-theme-icon]");
      if (icon) icon.textContent = isDark ? "☀️" : "🌙";
    },
  };

  Theme.init();
  window.Theme = Theme;
})();
