import { createApp } from 'vue'
import { createPinia } from 'pinia'

import './style.css'
import App from './App.vue'
import reveal from './directives/reveal'
import router from './router'
import { initAnalytics } from './utils/analytics'
import { initErrorTracking } from './utils/errorTracking'

initAnalytics()
const app = createApp(App)
initErrorTracking(app, router)
app.use(createPinia()).use(router).directive('reveal', reveal).mount('#app')
