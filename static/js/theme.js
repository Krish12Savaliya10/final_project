const TOURGEN_THEME_KEY = "tourgenTheme";

function getSavedTheme() {
  const saved = localStorage.getItem(TOURGEN_THEME_KEY);
  if (saved === "dark" || saved === "light") {
    return saved;
  }
  return "light";
}

function updateToggleButtons(theme) {
  const isDark = theme === "dark";
  const buttons = document.querySelectorAll("[data-theme-toggle]");
  buttons.forEach((btn) => {
    const icon = btn.querySelector("i");
    if (icon) {
      icon.className = isDark ? "bi bi-sun" : "bi bi-moon-stars";
    }
    const label = btn.querySelector("[data-theme-label]");
    if (label) {
      label.textContent = isDark ? "Light Mode" : "Dark Mode";
    }
  });
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  document.body.classList.toggle("dark-mode", theme === "dark");
  updateToggleButtons(theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  localStorage.setItem(TOURGEN_THEME_KEY, next);
  applyTheme(next);
}

document.addEventListener("DOMContentLoaded", () => {
  applyTheme(getSavedTheme());
  document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
    btn.addEventListener("click", toggleTheme);
  });
});
