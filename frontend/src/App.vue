<script setup>
import { useRoute } from 'vue-router'

import NavBar from './components/NavBar.vue'
import Footer from './components/Footer.vue'
import AnnouncementBanner from './components/AnnouncementBanner.vue'
import ImpersonationBanner from './components/ImpersonationBanner.vue'

const route = useRoute()
</script>

<template>
  <div class="flex min-h-screen flex-col bg-page">
    <!-- Invisible until focused - lets a keyboard or screen-reader user jump straight past the
    nav (and announcement banner, on pages that have one) to the actual page content, instead of
    tabbing through every nav link on every single page load. -->
    <a
      href="#main-content"
      class="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-accent-bg focus:px-4 focus:py-2 focus:font-semibold focus:text-on-accent"
    >
      Skip to content
    </a>
    <!-- Outside the hideChrome gate on purpose - a superadmin impersonating a customer sees the
    public site (hideChrome false), but impersonating a driver lands them in the driver portal
    (hideChrome true), so this needs to stay visible in every layout regardless. -->
    <ImpersonationBanner />
    <NavBar v-if="!route.meta.hideChrome" />
    <AnnouncementBanner v-if="!route.meta.hideChrome" />
    <main id="main-content" class="flex-1">
      <RouterView />
    </main>
    <Footer v-if="!route.meta.hideChrome" />
  </div>
</template>
