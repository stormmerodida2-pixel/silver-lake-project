<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth.js'
import { confirmDialog } from '../utils/dialogs'
import NotificationBell from './NotificationBell.vue'
import SilverLakeLogo from './SilverLakeLogo.vue'

const isOpen = ref(false)
const mobileMenuButton = ref(null)
const mobileMenuPanel = ref(null)
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

watch(
  () => route.path,
  () => {
    isOpen.value = false
  },
)

function handleOutsideClick(event) {
  if (
    mobileMenuButton.value &&
    !mobileMenuButton.value.contains(event.target) &&
    mobileMenuPanel.value &&
    !mobileMenuPanel.value.contains(event.target)
  ) {
    isOpen.value = false
  }
}

// The nav bar is hidden (and unmounted) on the driver portal, so this fires again the moment
// someone navigates back to the main site - catching any role change (e.g. a driver
// application getting approved) that happened since they last logged in.
onMounted(() => {
  auth.refreshProfile()
  document.addEventListener('click', handleOutsideClick)
})
onUnmounted(() => {
  document.removeEventListener('click', handleOutsideClick)
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
    <nav class="mx-auto flex max-w-6xl items-center gap-4 px-4 py-4 sm:px-6 lg:gap-8">
      <RouterLink to="/" class="flex shrink-0 items-center gap-2">
        <SilverLakeLogo :size="32" />
        <span class="hidden flex-col items-start leading-none sm:flex">
          <span class="font-[Georgia] text-sm font-bold uppercase tracking-wide text-white">SilverLake</span>
          <span
            class="mt-0.5 border-b border-gold-500 pb-0.5 text-[8px] font-bold uppercase tracking-[0.2em] text-slate-400"
          >
            Car Rentals
          </span>
        </span>
      </RouterLink>

      <div class="hidden items-center gap-4 md:flex lg:gap-8">
        <RouterLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="whitespace-nowrap font-[Georgia] text-base font-semibold tracking-wide text-slate-200 transition hover:text-gold-400"
          active-class="text-gold-400"
        >
          {{ link.label }}
        </RouterLink>
      </div>

      <div class="ml-auto flex shrink-0 items-center gap-3">
        <div class="hidden items-center gap-4 md:flex lg:gap-6">
          <template v-if="auth.isAuthenticated">
            <RouterLink
              to="/account/profile"
              class="flex items-center gap-2 whitespace-nowrap font-[Georgia] text-base tracking-wide text-slate-400 transition hover:text-gold-400"
            >
              <span class="h-7 w-7 shrink-0 overflow-hidden rounded-full border border-navy-700 bg-navy-800">
                <img v-if="auth.user?.avatar" :src="auth.user.avatar" alt="" class="h-full w-full object-cover" />
                <span v-else class="flex h-full w-full items-center justify-center text-xs font-bold text-gold-400">
                  {{ (auth.user?.first_name || '?')[0] }}
                </span>
              </span>
              Hi, {{ auth.user?.first_name || 'there' }}
            </RouterLink>
          </template>
          <template v-else>
            <RouterLink
              to="/login"
              class="whitespace-nowrap font-[Georgia] text-base font-semibold tracking-wide text-slate-200 transition hover:text-gold-400"
            >
              Log In
            </RouterLink>
            <RouterLink
              to="/register"
              class="whitespace-nowrap rounded-md bg-gold-500 px-3 py-1.5 font-[Georgia] text-base font-semibold tracking-wide text-navy-950 transition hover:bg-gold-400"
            >
              Sign Up
            </RouterLink>
          </template>
        </div>

        <NotificationBell v-if="auth.isAuthenticated" base-path="/notifications" />

        <button
          v-if="auth.isAuthenticated"
          class="hidden whitespace-nowrap font-[Georgia] text-base font-semibold tracking-wide text-slate-200 transition hover:text-gold-400 md:block"
          @click="handleLogout"
        >
          Log Out
        </button>

        <button
          ref="mobileMenuButton"
          class="flex h-9 w-9 items-center justify-center rounded-full text-slate-200 transition hover:bg-navy-800 hover:text-gold-400 md:hidden"
          aria-label="Toggle menu"
          :aria-expanded="isOpen"
          @click.stop="isOpen = !isOpen"
        >
          <!-- .stop matters: without it, this click reaches handleOutsideClick with a detached event.target (the icon swaps via v-if/v-else the instant isOpen flips), which immediately re-closes the menu it just opened. -->
          <svg
            v-if="!isOpen"
            xmlns="http://www.w3.org/2000/svg"
            class="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
          <svg
            v-else
            xmlns="http://www.w3.org/2000/svg"
            class="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </nav>

    <div
      v-if="isOpen"
      ref="mobileMenuPanel"
      data-testid="mobile-nav-panel"
      class="flex flex-col gap-1 border-t border-navy-800 px-4 py-3 md:hidden"
    >
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
