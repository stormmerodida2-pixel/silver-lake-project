<script setup>
import { useRoute } from 'vue-router'

import NavBar from './components/NavBar.vue'
import Footer from './components/Footer.vue'
import AnnouncementBanner from './components/AnnouncementBanner.vue'
import ImpersonationBanner from './components/ImpersonationBanner.vue'

const route = useRoute()
</script>

<template>
  <div class="flex min-h-screen flex-col bg-white">
    <!-- Outside the hideChrome gate on purpose - a superadmin impersonating a customer sees the
    public site (hideChrome false), but impersonating a driver lands them in the driver portal
    (hideChrome true), so this needs to stay visible in every layout regardless. -->
    <ImpersonationBanner />
    <NavBar v-if="!route.meta.hideChrome" />
    <div v-if="!route.meta.hideChrome" class="mx-auto w-full max-w-6xl px-4 pt-4 sm:px-6">
      <AnnouncementBanner />
    </div>
    <main class="flex-1">
      <RouterView />
    </main>
    <Footer v-if="!route.meta.hideChrome" />
  </div>
</template>
