<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import SilverLakeLogo from './SilverLakeLogo.vue'

const isOpen = ref(false)
const auth = useAuthStore()
const router = useRouter()

const links = computed(() => {
  const base = [
    { to: '/', label: 'Home' },
    { to: '/fleet', label: 'Fleet' },
    { to: '/drivers', label: 'Drivers' },
    { to: '/contact', label: 'Contact' },
  ]
  if (auth.isAuthenticated) {
    base.splice(3, 0, { to: '/account/bookings', label: 'My Bookings' })
  }
  if (auth.user?.is_staff) {
    base.push({ to: '/admin', label: 'Admin' })
  }
  return base
})

function handleLogout() {
  auth.logout()
  isOpen.value = false
  router.push('/')
}
</script>

<template>
  <header class="sticky top-0 z-40 border-b border-navy-800 bg-navy-950/95 backdrop-blur">
    <nav class="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3 sm:px-6">
      <RouterLink to="/" class="flex items-center gap-2">
        <SilverLakeLogo :size="32" />
        <span class="flex items-baseline gap-2">
          <span class="font-[Georgia] text-xl font-bold tracking-wide text-white">SILVERLAKE</span>
          <span class="hidden text-xs tracking-widest text-gold-400 sm:inline">CAR RENTALS</span>
        </span>
      </RouterLink>

      <div class="hidden items-center gap-6 md:flex">
        <RouterLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="text-sm font-medium text-slate-200 transition hover:text-gold-400"
          active-class="text-gold-400"
        >
          {{ link.label }}
        </RouterLink>
      </div>

      <div class="ml-auto hidden items-center gap-4 md:flex">
        <template v-if="auth.isAuthenticated">
          <span class="text-sm text-slate-400">Hi, {{ auth.user?.first_name || 'there' }}</span>
          <button class="text-sm font-medium text-slate-200 transition hover:text-gold-400" @click="handleLogout">
            Log Out
          </button>
        </template>
        <template v-else>
          <RouterLink to="/login" class="text-sm font-medium text-slate-200 transition hover:text-gold-400">
            Log In
          </RouterLink>
          <RouterLink
            to="/register"
            class="rounded-md bg-gold-500 px-3 py-1.5 text-sm font-semibold text-navy-950 transition hover:bg-gold-400"
          >
            Sign Up
          </RouterLink>
        </template>
      </div>

      <button
        class="ml-auto text-slate-200 md:hidden"
        aria-label="Toggle menu"
        @click="isOpen = !isOpen"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
    </nav>

    <div v-if="isOpen" class="flex flex-col gap-1 border-t border-navy-800 px-4 py-3 md:hidden">
      <RouterLink
        v-for="link in links"
        :key="link.to"
        :to="link.to"
        class="rounded px-2 py-2 text-sm font-medium text-slate-200 hover:bg-navy-800 hover:text-gold-400"
        @click="isOpen = false"
      >
        {{ link.label }}
      </RouterLink>

      <div class="mt-2 border-t border-navy-800 pt-2">
        <template v-if="auth.isAuthenticated">
          <button
            class="w-full rounded px-2 py-2 text-left text-sm font-medium text-slate-200 hover:bg-navy-800 hover:text-gold-400"
            @click="handleLogout"
          >
            Log Out
          </button>
        </template>
        <template v-else>
          <RouterLink
            to="/login"
            class="block rounded px-2 py-2 text-sm font-medium text-slate-200 hover:bg-navy-800 hover:text-gold-400"
            @click="isOpen = false"
          >
            Log In
          </RouterLink>
          <RouterLink
            to="/register"
            class="block rounded px-2 py-2 text-sm font-medium text-slate-200 hover:bg-navy-800 hover:text-gold-400"
            @click="isOpen = false"
          >
            Sign Up
          </RouterLink>
        </template>
      </div>
    </div>
  </header>
</template>
