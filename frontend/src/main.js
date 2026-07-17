import { createApp } from 'vue'
import { createPinia } from 'pinia'

import './style.css'
import App from './App.vue'
import reveal from './directives/reveal'
import router from './router'
import { initAnalytics } from './utils/analytics'

initAnalytics()
createApp(App).use(createPinia()).use(router).directive('reveal', reveal).mount('#app')
