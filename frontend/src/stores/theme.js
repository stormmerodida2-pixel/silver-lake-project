import { defineStore } from 'pinia'

const STORAGE_KEY = 'sl_theme'
const DARK_THEME_COLOR = '#0a1730'
const LIGHT_THEME_COLOR = '#f6efdd'

// Site is dark-by-brand-default - a first-time visitor sees the same navy/gold look the site
// has always had, regardless of their OS color-scheme preference. Only an explicit prior
// toggle (persisted below) switches that. Mirrors index.html's own inline FOUC-prevention
// script, which sets the same class before first paint using the same storage key.
function applyThemeClass(theme) {
  document.documentElement.classList.toggle('light', theme === 'light')
  document.documentElement.classList.toggle('dark', theme === 'dark')
  document.documentElement.style.colorScheme = theme
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', theme === 'dark' ? DARK_THEME_COLOR : LIGHT_THEME_COLOR)
}

export const useThemeStore = defineStore('theme', {
  state: () => ({
    theme: localStorage.getItem(STORAGE_KEY) || 'dark',
  }),
  actions: {
    setTheme(theme) {
      this.theme = theme
      localStorage.setItem(STORAGE_KEY, theme)
      applyThemeClass(theme)
    },
    toggleTheme() {
      this.setTheme(this.theme === 'dark' ? 'light' : 'dark')
    },
    // Called once at boot (see main.js) to re-apply the class/meta-color/color-scheme that
    // index.html's inline script already set before paint, so it's driven by the same Pinia
    // state the rest of the app reads rather than left as a one-off DOM mutation.
    init() {
      applyThemeClass(this.theme)
    },
  },
})
