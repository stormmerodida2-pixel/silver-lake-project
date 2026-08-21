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
      <div class="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 lg:grid-cols-3">
        <div>
          <h4 class="text-sm font-semibold uppercase tracking-wide text-accent">Book Your Ride Today</h4>
          <div class="mt-3 flex flex-col gap-2 text-sm">
            <a href="tel:+254798184193" class="flex items-center gap-2 text-foreground hover:text-accent">
              <svg class="h-4 w-4 shrink-0 text-accent" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M3 5a2 2 0 0 1 2-2h3.28a1 1 0 0 1 .948.684l1.498 4.493a1 1 0 0 1-.502 1.21l-2.257 1.13a11.042 11.042 0 0 0 5.516 5.516l1.13-2.257a1 1 0 0 1 1.21-.502l4.493 1.498A1 1 0 0 1 21 16.72V19a2 2 0 0 1-2 2h-1C9.716 21 3 14.284 3 6V5Z"
                />
              </svg>
              0798 184 193
            </a>
            <a
              href="https://wa.me/254710315345?text=Hello%20SilverLake%20Car%20Rentals%2C%20I%27d%20like%20to%20book%20a%20car."
              target="_blank"
              rel="noopener noreferrer"
              class="flex items-center gap-2 text-foreground hover:text-success"
            >
              <svg class="h-4 w-4 shrink-0 text-success" fill="currentColor" viewBox="0 0 24 24">
                <path
                  d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413Z"
                />
              </svg>
              0710 315 345
            </a>
            <p class="flex items-center gap-2 text-foreground-muted">
              <svg class="h-4 w-4 shrink-0 text-accent" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M12 21s6-5.2 6-10.5A6 6 0 0 0 6 10.5C6 15.8 12 21 12 21Z"
                />
                <circle cx="12" cy="10.5" r="2.2" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
              Kisumu, Kenya
            </p>
          </div>
        </div>

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
