import { createApp } from 'vue'
import { createPinia } from 'pinia'

import './style.css'
import App from './App.vue'
import reveal from './directives/reveal'
import router from './router'
import { useThemeStore } from './stores/theme'
import { initAnalytics } from './utils/analytics'
import { initClientErrorReporting } from './utils/clientErrorReporting'
import { initErrorTracking } from './utils/errorTracking'
import { registerServiceWorker } from './utils/pushNotifications'

const app = createApp(App)
// Skipped when the build-time prerender script (scripts/prerender.mjs) is visiting this page -
// analytics/error-tracking/push registration have no business firing for a headless crawl of
// every public route on every deploy, which would otherwise permanently pollute real GA/Sentry
// data with bot traffic. See main.js's own window.__PRERENDERING__ flag, set via Playwright's
// page.addInitScript() before each page.goto().
if (!window.__PRERENDERING__) {
  initAnalytics()
  initClientErrorReporting()
  registerServiceWorker()
  initErrorTracking(app, router)
}
app.use(createPinia()).use(router).directive('reveal', reveal).mount('#app')
useThemeStore().init()
