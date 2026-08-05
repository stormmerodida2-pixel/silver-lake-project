<script setup>
import SilverLakeLogo from './SilverLakeLogo.vue'

const year = new Date().getFullYear()

const destinations = ['Nairobi', 'Mombasa', 'Nakuru', 'Eldoret', 'Malindi', 'And beyond...']

const featureStrip = [
  { title: 'Clean & Well Maintained', icon: 'car' },
  { title: 'Fully Insured', icon: 'shield' },
  { title: '24/7 Customer Support', icon: 'headset' },
  { title: 'Flexible Options', icon: 'sliders' },
]
</script>

<template>
  <footer class="border-t border-border-subtle bg-surface">
    <div class="border-t border-border-subtle bg-page/40">
      <div class="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 lg:grid-cols-2">
        <div>
          <h4 class="text-sm font-semibold uppercase tracking-wide text-accent">Payment Options</h4>
          <div class="mt-3 max-w-xs rounded-lg border border-border bg-surface px-4 py-3">
            <p class="text-xs font-semibold uppercase tracking-wide text-brand-blue-400">Bank Transfer</p>
            <p class="mt-1 text-xs text-foreground-muted">Co-operative Bank of Kenya</p>
            <p class="text-xs text-foreground-muted">Paybill <span class="font-semibold text-foreground">400200</span></p>
            <p class="text-xs text-foreground-muted">A/C No: <span class="font-semibold text-foreground">01101465587001</span></p>
          </div>
        </div>

        <div>
          <h4 class="text-sm font-semibold uppercase tracking-wide text-accent">We Take You Across Kenya</h4>
          <ul class="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm text-foreground-secondary">
            <li v-for="place in destinations" :key="place" class="flex items-center gap-1.5">
              <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-blue-400"></span>
              {{ place }}
            </li>
          </ul>
          <p class="mt-2 text-xs text-foreground-subtle">One call, countless destinations.</p>
        </div>
      </div>

      <div class="border-t border-border-subtle">
        <div class="mx-auto grid max-w-6xl gap-6 px-4 py-8 sm:grid-cols-2 sm:px-6 lg:grid-cols-4">
          <div v-for="feature in featureStrip" :key="feature.title" class="flex items-center gap-3">
            <span
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-accent-border/40 bg-surface text-accent"
            >
              <svg
                v-if="feature.icon === 'car'"
                class="h-4.5 w-4.5"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M4 16l1.5-5.5A2 2 0 0 1 7.4 9h9.2a2 2 0 0 1 1.9 1.5L20 16"
                />
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M3.5 16h17v3a1 1 0 0 1-1 1H16a1 1 0 0 1-1-1v-1H9v1a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1v-3Z"
                />
                <circle cx="7.5" cy="16" r="1.4" />
                <circle cx="16.5" cy="16" r="1.4" />
              </svg>
              <svg
                v-else-if="feature.icon === 'shield'"
                class="h-4.5 w-4.5"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M12 3.5l6.5 2.5v4.8c0 4.6-2.9 8-6.5 9.7-3.6-1.7-6.5-5.1-6.5-9.7V6l6.5-2.5z"
                />
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.3l2 2 4.5-4.5" />
              </svg>
              <svg
                v-else-if="feature.icon === 'headset'"
                class="h-4.5 w-4.5"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 13v-1a8 8 0 0 1 16 0v1" />
                <rect x="3" y="13" width="4" height="6" rx="1.2" />
                <rect x="17" y="13" width="4" height="6" rx="1.2" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M19 19v1a2 2 0 0 1-2 2h-3" />
              </svg>
              <svg v-else class="h-4.5 w-4.5" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h9M17 6h3M4 12h3M9 12h11M4 18h13M19 18h1" />
                <circle cx="13.5" cy="6" r="1.8" />
                <circle cx="7" cy="12" r="1.8" />
                <circle cx="16.5" cy="18" r="1.8" />
              </svg>
            </span>
            <span class="text-sm font-medium text-foreground">{{ feature.title }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="border-t border-border-subtle">
      <div
        class="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-6 text-sm sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-x-10 sm:gap-y-4 sm:px-6"
      >
        <div class="flex items-center gap-2">
          <SilverLakeLogo :size="22" />
          <span class="font-[Georgia] font-bold text-foreground">SilverLake Car Rentals</span>
        </div>

        <div class="flex flex-wrap gap-x-6 gap-y-2 text-foreground-secondary">
          <a href="mailto:info@silverlakecarrentals.co.ke" class="hover:text-accent"
            >info@silverlakecarrentals.co.ke</a
          >
          <RouterLink to="/contact" class="hover:text-accent">Contact Us</RouterLink>
          <RouterLink to="/drivers" class="hover:text-accent">Meet Our Drivers</RouterLink>
          <RouterLink to="/terms" class="hover:text-accent">Terms of Service</RouterLink>
          <RouterLink to="/privacy" class="hover:text-accent">Privacy Policy</RouterLink>
          <RouterLink to="/refund-policy" class="hover:text-accent">Refund &amp; Cancellation</RouterLink>
          <RouterLink to="/faq" class="hover:text-accent">FAQ</RouterLink>
        </div>
      </div>
    </div>

    <div class="border-t border-border-subtle bg-page py-3 text-center">
      <p class="text-xs font-semibold uppercase tracking-widest text-accent/90">
        Safe Journeys. Happy Clients. Every Time.
      </p>
    </div>
    <div class="border-t border-border-subtle py-4 text-center text-xs text-foreground-subtle">
      &copy; {{ year }} SilverLake Car Rentals. All rights reserved.
    </div>
  </footer>
</template>
