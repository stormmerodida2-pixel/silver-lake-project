import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  test: {
    environment: 'jsdom',
    // Playwright's e2e/ suite is a separate, real-browser-against-a-real-backend layer (see
    // playwright.config.js) - excluded here so `vitest run` never tries to treat those specs as
    // unit tests (they need a running dev server and seeded DB, neither of which exists in a
    // plain Vitest run).
    exclude: ['e2e/**', 'node_modules/**'],
  },
})
