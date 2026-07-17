<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth.js'
import { confirmDialog } from '../utils/dialogs'
import NotificationBell from './NotificationBell.vue'
import SilverLakeLogo from './SilverLakeLogo.vue'

const isOpen = ref(false)
const auth = useAuthStore()
const router = useRouter()

// The nav bar is hidden (and unmounted) on the driver portal, so this fires again the moment
// someone navigates back to the main site - catching any role change (e.g. a driver
// application getting approved) that happened since they last logged in.
onMounted(() => {
  auth.refreshProfile()
})

const links = computed(() => {
  const base = [
    { to: '/', label: 'Home' },
    { to: '/fleet', label: 'Fleet' },
    { to: '/blog', label: 'Blog' },
    { to: '/contact', label: 'Contact' },
  ]
  if (auth.isAuthenticated) {
    base.splice(2, 0, { to: '/account/bookings', label: 'My Bookings' })
  }
  if (auth.user?.driver_status === 'active') {
    base.push({ to: '/driver', label: 'Driver Dashboard' })
  }
  if (auth.user?.is_staff) {
    base.push({ to: '/admin', label: 'Admin' })
  }
  return base
})

async function handleLogout() {
  if (!(await confirmDialog('Are you sure you want to log out?'))) return
  auth.logout()
  isOpen.value = false
  router.push('/')
}
</script>

<template>
  <header class="sticky top-0 z-40 border-b border-navy-800 bg-navy-950/95 backdrop-blur">
    <nav class="mx-auto flex max-w-6xl items-center gap-10 px-4 py-4 sm:px-6">
      <RouterLink to="/" class="flex items-center gap-2">
        <SilverLakeLogo :size="32" />
      </RouterLink>

      <div class="hidden items-center gap-10 md:flex">
        <RouterLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="font-[Georgia] text-base font-semibold tracking-wide text-slate-200 transition hover:text-gold-400"
          active-class="text-gold-400"
        >
          {{ link.label }}
        </RouterLink>
      </div>

      <div class="ml-auto hidden items-center gap-6 md:flex">
        <template v-if="auth.isAuthenticated">
          <RouterLink to="/account/profile" class="flex items-center gap-2 font-[Georgia] text-base tracking-wide text-slate-400 transition hover:text-gold-400">
            <span class="h-7 w-7 shrink-0 overflow-hidden rounded-full border border-navy-700 bg-navy-800">
              <img v-if="auth.user?.avatar" :src="auth.user.avatar" alt="" class="h-full w-full object-cover" />
              <span v-else class="flex h-full w-full items-center justify-center text-xs font-bold text-gold-400">
                {{ (auth.user?.first_name || '?')[0] }}
              </span>
            </span>
            Hi, {{ auth.user?.first_name || 'there' }}
          </RouterLink>
          <button class="font-[Georgia] text-base font-semibold tracking-wide text-slate-200 transition hover:text-gold-400" @click="handleLogout">
            Log Out
          </button>
        </template>
        <template v-else>
          <RouterLink to="/login" class="font-[Georgia] text-base font-semibold tracking-wide text-slate-200 transition hover:text-gold-400">
            Log In
          </RouterLink>
          <RouterLink
            to="/register"
            class="rounded-md bg-gold-500 px-3 py-1.5 font-[Georgia] text-base font-semibold tracking-wide text-navy-950 transition hover:bg-gold-400"
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

      <NotificationBell v-if="auth.isAuthenticated" base-path="/notifications" />
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
          <RouterLink
            to="/account/profile"
            class="block rounded px-2 py-2 text-sm font-medium text-slate-200 hover:bg-navy-800 hover:text-gold-400"
            @click="isOpen = false"
          >
            My Profile
          </RouterLink>
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
