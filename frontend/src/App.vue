<script setup>
import { useRoute } from 'vue-router'

import NavBar from './components/NavBar.vue'
import Footer from './components/Footer.vue'
import WhatsAppButton from './components/WhatsAppButton.vue'

const route = useRoute()
</script>

<template>
  <div class="flex min-h-screen flex-col bg-white">
    <NavBar v-if="!route.meta.hideChrome" />
    <main class="flex-1">
      <RouterView />
    </main>
    <template v-if="!route.meta.hideChrome">
      <Footer />
      <WhatsAppButton />
    </template>
  </div>
</template>
