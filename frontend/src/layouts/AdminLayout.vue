<script setup>
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import SilverLakeLogo from '../components/SilverLakeLogo.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const navItems = [
  {
    to: '/admin',
    label: 'Dashboard',
    icon: 'M3 13h4v8H3v-8Zm7-7h4v15h-4V6Zm7 4h4v11h-4V10Z',
  },
  {
    to: '/admin/users',
    label: 'Users',
    icon: 'M17 20h5v-2a4 4 0 0 0-3-3.87M9 20H4v-2a4 4 0 0 1 3-3.87m5-2.13a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm7-4a4 4 0 0 1-3 3.87',
  },
  {
    to: '/admin/bookings',
    label: 'Bookings',
    icon: 'M8 3v4M16 3v4M4 9h16M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z',
  },
  {
    to: '/admin/drivers',
    label: 'Drivers',
    icon: 'M5 17h14M6 17l1.5-5h9L18 17M9 12V8h6v4M10 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm5 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z',
  },
  {
    to: '/admin/payouts',
    label: 'Payouts',
    icon: 'M12 8c-1.66 0-3 .9-3 2s1.34 2 3 2 3 .9 3 2-1.34 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 2v8m0 0v2m0-2c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  },
]

function handleLogout() {
  auth.logout()
  router.push('/')
}
</script>

<template>
  <div class="flex min-h-screen bg-navy-950">
    <aside class="hidden w-56 shrink-0 flex-col border-r border-navy-800 bg-navy-900 md:flex">
      <RouterLink to="/" class="flex items-center gap-2 border-b border-navy-800 px-5 py-4">
        <SilverLakeLogo :size="26" />
        <span class="font-[Georgia] text-sm font-bold tracking-wide text-white">SilverLake Admin</span>
      </RouterLink>

      <nav class="flex flex-1 flex-col gap-1 p-3">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition"
          :class="
            route.path === item.to
              ? 'bg-gold-500 text-navy-950'
              : 'text-slate-300 hover:bg-navy-800 hover:text-gold-400'
          "
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
            <path stroke-linecap="round" stroke-linejoin="round" :d="item.icon" />
          </svg>
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="border-t border-navy-800 p-3">
        <RouterLink
          to="/"
          class="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-slate-300 transition hover:bg-navy-800 hover:text-gold-400"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
            <path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          Back to Site
        </RouterLink>
        <button
          class="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm font-medium text-slate-300 transition hover:bg-navy-800 hover:text-gold-400"
          @click="handleLogout"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
            <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 5v1a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3h4a3 3 0 0 1 3 3v1" />
          </svg>
          Log Out
        </button>
      </div>
    </aside>

    <div class="flex-1">
      <header class="flex items-center justify-between border-b border-navy-800 bg-navy-950/95 px-4 py-3 backdrop-blur md:px-8">
        <div class="flex items-center gap-2 md:hidden">
          <SilverLakeLogo :size="24" />
          <span class="font-[Georgia] text-sm font-bold text-white">Admin</span>
        </div>
        <div class="hidden text-sm text-slate-400 md:block">{{ route.meta.pageTitle || 'Admin Panel' }}</div>
        <div class="flex items-center gap-3 text-sm text-slate-300">
          <span>Hi, {{ auth.user?.first_name || 'Admin' }}</span>
        </div>
      </header>

      <nav class="flex gap-1 overflow-x-auto border-b border-navy-800 bg-navy-900 px-3 py-2 md:hidden">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="shrink-0 rounded-md px-3 py-1.5 text-xs font-semibold"
          :class="route.path === item.to ? 'bg-gold-500 text-navy-950' : 'text-slate-300'"
        >
          {{ item.label }}
        </RouterLink>
      </nav>

      <main class="px-4 py-8 md:px-8">
        <RouterView />
      </main>
    </div>
  </div>
</template>
