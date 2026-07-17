<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AnnouncementBanner from '../components/AnnouncementBanner.vue'
import NotificationBell from '../components/NotificationBell.vue'
import SilverLakeLogo from '../components/SilverLakeLogo.vue'
import { useAuthStore } from '../stores/auth'
import { useDriverPortalStore } from '../stores/driverPortal'
import { confirmDialog } from '../utils/dialogs'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const driverPortal = useDriverPortalStore()

const navItems = [
  {
    to: '/driver',
    label: 'Dashboard',
    icon: 'M3 13h4v8H3v-8Zm7-7h4v15h-4V6Zm7 4h4v11h-4V10Z',
  },
  {
    to: '/driver/vehicles',
    label: 'My Vehicles',
    icon: 'M5 17h14M6 17l1.5-5h9L18 17M9 12V8h6v4M10 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm5 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z',
  },
  {
    to: '/driver/bookings',
    label: 'My Bookings',
    icon: 'M8 3v4M16 3v4M4 9h16M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z',
  },
]

async function handleLogout() {
  if (!(await confirmDialog('Are you sure you want to log out?'))) return
  auth.logout()
  router.push('/')
}

// Mobile nav: a dropdown panel instead of the old horizontally-scrolling strip, which hid most
// items off-screen with no visual hint more existed. Closes on navigation so it never lingers
// open over the next page - but route.path alone doesn't fire for a link back to the current
// page, and gives no way to dismiss it by tapping elsewhere, so every link also closes it
// directly and a document-level click handler closes it on any click outside both the toggle
// button and the panel itself (same pattern as NotificationBell.vue).
const mobileMenuOpen = ref(false)
const mobileMenuButton = ref(null)
const mobileMenuPanel = ref(null)
watch(() => route.path, () => {
  mobileMenuOpen.value = false
})

function handleMobileMenuOutsideClick(event) {
  if (
    mobileMenuButton.value && !mobileMenuButton.value.contains(event.target) &&
    mobileMenuPanel.value && !mobileMenuPanel.value.contains(event.target)
  ) {
    mobileMenuOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleMobileMenuOutsideClick)
})
onUnmounted(() => {
  document.removeEventListener('click', handleMobileMenuOutsideClick)
})

// ── Away / Available toggle (profile hero, shown on every driver page) ──────
const awaySaving = ref(false)
const awayReasonDraft = ref('')
const showAwayForm = ref(false)
const awayError = ref('')

function openAwayForm() {
  awayReasonDraft.value = ''
  showAwayForm.value = true
}

async function markAway() {
  if (!awayReasonDraft.value.trim()) return
  awaySaving.value = true
  awayError.value = ''
  try {
    await driverPortal.markAway(awayReasonDraft.value.trim())
    showAwayForm.value = false
  } catch (err) {
    awayError.value = 'Could not update your availability.'
  } finally {
    awaySaving.value = false
  }
}

async function markAvailable() {
  awaySaving.value = true
  awayError.value = ''
  try {
    await driverPortal.markAvailable()
  } catch (err) {
    awayError.value = 'Could not update your availability.'
  } finally {
    awaySaving.value = false
  }
}

onMounted(() => {
  driverPortal.loadAll()
})
</script>

<template>
  <div class="flex min-h-screen bg-navy-950">
    <aside class="hidden w-56 shrink-0 flex-col border-r border-navy-800 bg-navy-900 md:flex">
      <RouterLink to="/" class="flex items-center gap-2 border-b border-navy-800 px-5 py-4">
        <SilverLakeLogo :size="26" />
        <span class="font-[Georgia] text-sm font-bold tracking-wide text-white">Driver Portal</span>
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
          to="/account/profile"
          class="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-slate-300 transition hover:bg-navy-800 hover:text-gold-400"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
            <path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM12 14a7 7 0 0 0-7 7h14a7 7 0 0 0-7-7Z" />
          </svg>
          My Profile
        </RouterLink>
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

    <div class="min-w-0 flex-1">
      <header class="flex items-center justify-between border-b border-navy-800 bg-navy-950/95 px-4 py-3 backdrop-blur md:px-8">
        <div class="flex items-center gap-2 md:hidden">
          <SilverLakeLogo :size="24" />
          <span class="font-[Georgia] text-sm font-bold text-white">Driver</span>
        </div>
        <div class="hidden text-sm text-slate-400 md:block">{{ route.meta.pageTitle || 'Driver Portal' }}</div>
        <div class="flex items-center gap-2 text-sm text-slate-300 sm:gap-3">
          <NotificationBell base-path="/driver/notifications" />
          <button
            ref="mobileMenuButton"
            class="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-slate-300 hover:bg-navy-800 hover:text-white md:hidden"
            :aria-expanded="mobileMenuOpen"
            aria-label="Toggle menu"
            @click.stop="mobileMenuOpen = !mobileMenuOpen"
          >
            <!-- .stop matters: without it, this click reaches handleMobileMenuOutsideClick with a detached event.target (the icon's path swaps via v-if/v-else the instant mobileMenuOpen flips), which immediately re-closes the menu it just opened. -->
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path v-if="!mobileMenuOpen" stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              <path v-else stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          <RouterLink
            to="/account/profile"
            class="hidden whitespace-nowrap font-[Georgia] text-sm tracking-wide transition hover:text-gold-400 sm:inline-block sm:text-base"
          >
            Hi, {{ auth.user?.first_name || 'Driver' }}
          </RouterLink>
        </div>
      </header>

      <div v-if="mobileMenuOpen" ref="mobileMenuPanel" class="border-b border-navy-800 bg-navy-900 md:hidden">
        <nav class="flex max-h-[60vh] flex-col gap-1 overflow-y-auto p-3">
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
            @click="mobileMenuOpen = false"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
              <path stroke-linecap="round" stroke-linejoin="round" :d="item.icon" />
            </svg>
            {{ item.label }}
          </RouterLink>
        </nav>
        <div class="border-t border-navy-800 p-3">
          <RouterLink
            to="/account/profile"
            class="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-slate-300 transition hover:bg-navy-800 hover:text-gold-400"
            @click="mobileMenuOpen = false"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
              <path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM12 14a7 7 0 0 0-7 7h14a7 7 0 0 0-7-7Z" />
            </svg>
            My Profile
          </RouterLink>
          <RouterLink
            to="/"
            class="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-slate-300 transition hover:bg-navy-800 hover:text-gold-400"
            @click="mobileMenuOpen = false"
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
      </div>

      <main class="px-4 py-8 md:px-8">
        <AnnouncementBanner class="mb-6" />

        <p v-if="driverPortal.profileLoading" class="text-center text-slate-400">Loading...</p>
        <p v-else-if="driverPortal.profileError" class="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {{ driverPortal.profileError }}
        </p>

        <template v-else-if="driverPortal.profile">
          <!-- Profile hero - persistent across every driver page -->
          <section class="overflow-hidden rounded-2xl border border-gold-500/40 bg-gradient-to-br from-navy-900 to-navy-950 p-6 sm:p-8">
            <div class="flex flex-wrap items-start justify-between gap-4">
              <div class="flex items-center gap-4">
                <div class="flex h-16 w-16 shrink-0 items-center justify-center rounded-full border border-gold-500/40 bg-gold-500/10 font-[Georgia] text-2xl font-bold text-gold-400">
                  {{ driverPortal.initials || '—' }}
                </div>
                <div>
                  <h2 class="font-[Georgia] text-2xl font-bold text-white">{{ driverPortal.profile.full_name }}</h2>
                  <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-400">
                    <span class="inline-flex items-center gap-1 text-gold-400">
                      <span v-for="n in 5" :key="n" class="text-sm leading-none">{{ n <= Math.round(driverPortal.profile.rating) ? '★' : '☆' }}</span>
                      <span class="ml-1 text-slate-300">{{ Number(driverPortal.profile.rating).toFixed(1) }}</span>
                    </span>
                    <span class="text-slate-600">&middot;</span>
                    <span>{{ driverPortal.profile.years_of_experience }} years experience</span>
                  </div>
                </div>
              </div>
              <span
                class="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold"
                :class="driverPortal.profile.is_away ? 'bg-red-500/10 text-red-400' : 'bg-emerald-500/10 text-emerald-400'"
              >
                <span class="h-1.5 w-1.5 rounded-full" :class="driverPortal.profile.is_away ? 'bg-red-400' : 'bg-emerald-400'" />
                {{ driverPortal.profile.is_away ? 'Away' : 'Available' }}
              </span>
            </div>

            <p v-if="driverPortal.profile.is_away && driverPortal.profile.away_reason" class="mt-4 rounded-lg bg-navy-800 px-4 py-3 text-sm text-slate-300">
              <span class="font-semibold text-slate-400">Your reason: </span>{{ driverPortal.profile.away_reason }}
            </p>
            <p class="mt-4 text-xs text-slate-500">
              While marked away, your vehicle(s) won't show up in the public fleet for customers to book.
              Admins can still see your reason.
            </p>
            <p v-if="awayError" class="mt-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ awayError }}</p>

            <div class="mt-4">
              <button
                v-if="!driverPortal.profile.is_away && !showAwayForm"
                class="rounded-md border border-red-400 px-4 py-2 text-sm font-semibold text-red-400 transition hover:bg-red-400 hover:text-navy-950"
                @click="openAwayForm"
              >
                Mark Myself Away
              </button>
              <button
                v-else-if="driverPortal.profile.is_away"
                :disabled="awaySaving"
                class="rounded-md bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-50"
                @click="markAvailable"
              >
                {{ awaySaving ? 'Updating...' : "I'm Available Again" }}
              </button>

              <div v-if="showAwayForm && !driverPortal.profile.is_away" class="mt-3 space-y-3">
                <textarea
                  v-model="awayReasonDraft"
                  rows="2"
                  placeholder="Reason (visible to admins only) - e.g. Sick leave until Friday"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                ></textarea>
                <div class="flex gap-3">
                  <button
                    class="rounded-md border border-navy-700 px-4 py-2 text-sm font-semibold text-slate-300 hover:border-slate-500"
                    @click="showAwayForm = false"
                  >
                    Cancel
                  </button>
                  <button
                    :disabled="awaySaving || !awayReasonDraft.trim()"
                    class="rounded-md bg-red-500 px-4 py-2 text-sm font-semibold text-white hover:bg-red-400 disabled:opacity-50"
                    @click="markAway"
                  >
                    {{ awaySaving ? 'Saving...' : 'Confirm Away' }}
                  </button>
                </div>
              </div>
            </div>
          </section>

          <div class="mt-6">
            <RouterView />
          </div>
        </template>
      </main>
    </div>
  </div>
</template>
