<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { useAuthStore } from '../stores/auth'
import { useCatalogStore } from '../stores/catalog'
import VehicleCard from '../components/VehicleCard.vue'
import ReviewCard from '../components/ReviewCard.vue'
import { setStructuredData } from '../utils/seo'

const auth = useAuthStore()
const catalog = useCatalogStore()

onMounted(() => {
  catalog.fetchVehicles()
  catalog.fetchReviews()
})

// Real, computed social proof - never a fabricated number. Hidden entirely until there's
// something genuine to show (a brand-new deployment with no trips/reviews yet just gets a
// hero with no stat strip, not a row of zeroes).
const totalTripsCompleted = computed(() =>
  catalog.vehicles.reduce((sum, vehicle) => sum + (vehicle.trips_completed || 0), 0),
)
const averageRating = computed(() => {
  if (!catalog.reviews.length) return null
  const total = catalog.reviews.reduce((sum, review) => sum + review.rating, 0)
  return (total / catalog.reviews.length).toFixed(1)
})
// AggregateRating must nest under the entity it rates, not stand alone - reuses the same @id
// as index.html's own static LocalBusiness block so this describes the same organization
// rather than a second, disconnected one. Guarded on real reviews existing at all (never emit
// a rating for zero reviews) and fires reactively once catalog.reviews finishes loading, not
// just once on mount - matches this file's own watcher idiom below.
watch(
  averageRating,
  (rating) => {
    if (!rating || !catalog.reviews.length) return
    setStructuredData('ld-dynamic-aggregate-rating', {
      '@context': 'https://schema.org',
      '@type': 'AutoRental',
      '@id': 'https://silverlakecarentals.com/#organization',
      name: 'SilverLake Car Rentals',
      url: 'https://silverlakecarentals.com/',
      aggregateRating: {
        '@type': 'AggregateRating',
        ratingValue: rating,
        reviewCount: catalog.reviews.length,
        bestRating: '5',
        worstRating: '1',
      },
    })
  },
  { immediate: true },
)
// The most-traveled photographed vehicles first - a genuine "this is our most popular ride"
// rather than an arbitrary first-in-list pick.
const photographedVehiclesByPopularity = computed(() =>
  [...catalog.vehicles.filter((vehicle) => vehicle.image)].sort(
    (a, b) => (b.trips_completed || 0) - (a.trips_completed || 0),
  ),
)

// Hero slowly cycles through real fleet photos rather than pinning one - restarts from the
// top and (re)starts the rotation timer whenever the list itself changes (e.g. once fetched).
const heroIndex = ref(0)
let heroTimer = null
watch(
  photographedVehiclesByPopularity,
  (vehicles) => {
    clearInterval(heroTimer)
    heroIndex.value = 0
    if (vehicles.length > 1) {
      heroTimer = setInterval(() => {
        heroIndex.value = (heroIndex.value + 1) % vehicles.length
      }, 4500)
    }
  },
  { immediate: true },
)
onUnmounted(() => clearInterval(heroTimer))
const heroVehicle = computed(() => photographedVehiclesByPopularity.value[heroIndex.value] || null)

const trustBadges = [
  { title: 'Safety', text: 'Your safety is our promise', icon: 'shield' },
  { title: 'People', text: 'Professional, friendly chauffeurs', icon: 'people' },
  { title: 'Punctuality', text: 'On time, every time', icon: 'clock' },
  { title: 'Hospitality', text: 'We treat you like family', icon: 'heart' },
  { title: 'Quality', text: 'Well maintained vehicles', icon: 'badge' },
]

const howItWorks = [
  { title: 'Browse & Choose', text: 'Explore the fleet and pick the vehicle that fits your trip.', icon: 'search' },
  {
    title: 'Book Your Dates',
    text: 'Reserve with a 30% deposit via M-Pesa or bank transfer - confirmed once received.',
    icon: 'calendar',
  },
  { title: 'Ride With Confidence', text: 'Meet your chauffeur or grab the keys - we handle the rest.', icon: 'wheel' },
]
</script>

<template>
  <div>
    <!-- Hero -->
    <section class="relative overflow-hidden border-b border-border-subtle bg-linear-to-b from-surface to-page">
      <div class="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-accent-bg/10 blur-3xl"></div>
      <div
        class="pointer-events-none absolute -left-32 bottom-0 h-72 w-72 rounded-full bg-brand-blue-500/10 blur-3xl"
      ></div>

      <div
        class="relative mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:gap-12 sm:px-6 sm:py-28 lg:grid-cols-2 lg:items-center"
      >
        <div>
          <p class="text-sm font-semibold uppercase tracking-widest text-accent">Kisumu &bull; Across Kenya</p>
          <h1 class="mt-3 max-w-2xl font-[Georgia] text-4xl font-bold leading-tight text-foreground sm:text-5xl">
            We don't just move you,
            <span class="text-accent">we elevate your journey.</span>
          </h1>
          <p class="mt-5 max-w-xl text-foreground-secondary">
            From the shores of Lake Victoria to every destination in Kenya, we deliver comfort, class and care in every
            mile.
          </p>

          <div class="mt-8 flex flex-wrap gap-4">
            <RouterLink
              to="/book?service=with_driver"
              class="rounded-md bg-accent-bg px-6 py-3 font-semibold text-on-accent shadow-lg shadow-gold-500/20 transition hover:-translate-y-0.5 hover:bg-accent-bg-hover hover:shadow-gold-500/30"
            >
              Book with Driver
            </RouterLink>
            <RouterLink
              to="/book?service=self_drive"
              class="rounded-md border border-accent-border px-6 py-3 font-semibold text-accent transition hover:-translate-y-0.5 hover:bg-surface-2"
            >
              Self Drive
            </RouterLink>
          </div>

          <dl
            v-if="catalog.vehicles.length || totalTripsCompleted > 0 || averageRating"
            class="mt-10 flex flex-wrap gap-x-10 gap-y-4 border-t border-border-subtle pt-6"
          >
            <div v-if="catalog.vehicles.length">
              <dt class="font-[Georgia] text-2xl font-bold text-foreground">{{ catalog.vehicles.length }}+</dt>
              <dd class="text-xs uppercase tracking-wide text-foreground-muted">Vehicles in the fleet</dd>
            </div>
            <div v-if="totalTripsCompleted > 0">
              <dt class="font-[Georgia] text-2xl font-bold text-foreground">{{ totalTripsCompleted }}+</dt>
              <dd class="text-xs uppercase tracking-wide text-foreground-muted">Trips completed</dd>
            </div>
            <div v-if="averageRating">
              <dt class="font-[Georgia] text-2xl font-bold text-foreground">
                {{ averageRating }}<span class="text-accent">&#9733;</span>
              </dt>
              <dd class="text-xs uppercase tracking-wide text-foreground-muted">Average rating</dd>
            </div>
          </dl>
        </div>

        <div v-if="heroVehicle" v-reveal class="relative mx-auto w-full max-w-xs sm:max-w-sm lg:max-w-lg">
          <!-- Stands in for the flyer's Lake Victoria sunset backdrop - a warm gradient glow,
               not a fabricated photo, sitting behind the real fleet photography. -->
          <div
            class="pointer-events-none absolute inset-0 -z-10 rounded-full bg-radial from-gold-500/25 via-brand-blue-500/10 to-transparent blur-3xl"
          ></div>

          <div class="relative">
            <!-- Thin corner brackets frame the card like a showcase spotlight - a small,
                 deliberate accent rather than a plain rectangle floating on the page. -->
            <span
              class="pointer-events-none absolute -left-3 -top-3 h-8 w-8 rounded-tl-xl border-l-2 border-t-2 border-accent-border/70 sm:h-10 sm:w-10"
            ></span>
            <span
              class="pointer-events-none absolute -bottom-3 -right-3 h-8 w-8 rounded-br-xl border-b-2 border-r-2 border-accent-border/70 sm:h-10 sm:w-10"
            ></span>

            <!-- Fleet photography is studio-shot on a white background, so it's set on its own
                 white card rather than cropped/blended into the navy hero - object-contain keeps
                 the whole vehicle visible (no cropped wheels/roof) and the white backdrop reads
                 as an intentional plinth instead of a leftover product-photo edge. -->
            <div class="relative overflow-hidden rounded-2xl bg-white shadow-2xl shadow-black/50 ring-1 ring-black/5">
              <span
                v-if="heroVehicle.trips_completed > 0"
                class="absolute right-3 top-3 z-10 inline-flex items-center gap-1 rounded-full bg-page/90 px-3 py-1.5 text-xs font-semibold text-accent shadow-lg backdrop-blur"
              >
                &#9733; Most popular ride
              </span>
              <Transition name="hero-fade" mode="out-in">
                <img
                  :key="heroVehicle.id"
                  :src="heroVehicle.image"
                  :alt="heroVehicle.name"
                  class="h-44 w-full object-contain p-4 sm:h-64 sm:p-6 lg:h-80"
                />
              </Transition>
            </div>

            <!-- Soft ground shadow gives the card a floating, podium feel. -->
            <div class="mx-auto -mt-2 h-5 w-4/5 rounded-full bg-page/60 blur-xl"></div>
          </div>

          <Transition name="hero-fade" mode="out-in">
            <p :key="heroVehicle.id" class="mt-5 text-center">
              <span class="font-[Georgia] text-lg font-bold text-foreground">{{ heroVehicle.name }}</span>
              <span class="ml-2 text-sm font-semibold text-accent">{{
                heroVehicle.category_name || heroVehicle.category
              }}</span>
            </p>
          </Transition>
        </div>
      </div>

      <svg
        class="absolute inset-x-0 -bottom-1 h-10 w-full text-navy-900"
        viewBox="0 0 1440 60"
        preserveAspectRatio="none"
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="M0,32 C240,60 480,0 720,20 C960,40 1200,10 1440,30 L1440,60 L0,60 Z" />
      </svg>
    </section>

    <!-- Rooted in Kisumu banner -->
    <section v-reveal class="border-b border-border-subtle bg-surface">
      <div class="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-2">
        <div>
          <h2 class="font-[Georgia] text-2xl font-bold text-foreground">
            Rooted in Kisumu. <span class="text-accent">Driven across Kenya.</span>
          </h2>
          <p class="mt-2 text-sm text-foreground-secondary">
            We are more than a car hire company. We are your travel partners. Anywhere. Anytime.
          </p>
        </div>
        <ul class="flex flex-col justify-center gap-4 text-sm text-foreground">
          <li class="flex items-center gap-3">
            <span
              class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-accent-border/40 bg-page text-accent"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M12 21s6-5.2 6-10.5A6 6 0 0 0 6 10.5C6 15.8 12 21 12 21Z"
                />
                <circle cx="12" cy="10.5" r="2.2" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
            Local Expertise
          </li>
          <li class="flex items-center gap-3">
            <span
              class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-accent-border/40 bg-page text-accent"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M3 17l4-7 3 4 3-6 5 9" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M3 20h18" />
              </svg>
            </span>
            National Reach
          </li>
          <li class="flex items-center gap-3">
            <span
              class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-accent-border/40 bg-page text-accent"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path
                  d="M12 21s-6.716-4.35-9.428-8.028C.86 10.42 1.02 7.36 3.343 5.6a5.5 5.5 0 0 1 7.657 1.02L12 7.8l1-1.18a5.5 5.5 0 0 1 7.657-1.02c2.323 1.76 2.483 4.82.77 7.372C18.716 16.65 12 21 12 21Z"
                />
              </svg>
            </span>
            Personal Touch
          </li>
        </ul>
      </div>
    </section>

    <!-- How it works -->
    <section v-reveal class="bg-page">
      <div class="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        <p class="text-center text-sm font-semibold uppercase tracking-widest text-accent">
          Simple, from booking to ride
        </p>
        <h2 class="mt-2 text-center font-[Georgia] text-3xl font-bold text-foreground">How It Works</h2>

        <div class="relative mt-10 grid gap-8 sm:mt-14 sm:grid-cols-3 sm:gap-10">
          <div class="absolute left-[16.5%] right-[16.5%] top-8 hidden h-px bg-surface-2 sm:block"></div>

          <div
            v-for="(step, index) in howItWorks"
            :key="step.title"
            class="relative flex flex-col items-center text-center"
          >
            <div
              class="relative z-10 flex h-14 w-14 items-center justify-center rounded-full border-2 border-accent-border bg-surface text-accent sm:h-16 sm:w-16"
            >
              <svg
                v-if="step.icon === 'search'"
                class="h-6 w-6"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                viewBox="0 0 24 24"
              >
                <circle cx="10.5" cy="10.5" r="6.5" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M20 20l-4.35-4.35" />
              </svg>
              <svg
                v-else-if="step.icon === 'calendar'"
                class="h-6 w-6"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                viewBox="0 0 24 24"
              >
                <rect x="4" y="5" width="16" height="15" rx="2" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 10h16M8 3v4M16 3v4" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 14.5l2 2 4-4.5" />
              </svg>
              <svg v-else class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="8.5" stroke-linecap="round" stroke-linejoin="round" />
                <circle cx="12" cy="12" r="2" stroke-linecap="round" stroke-linejoin="round" />
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M12 5.5v4M6.3 15.3l3.2-2.2M17.7 15.3l-3.2-2.2"
                />
              </svg>
            </div>
            <p class="mt-5 font-[Georgia] text-lg font-bold text-foreground">
              <span class="text-accent-strong">{{ String(index + 1).padStart(2, '0') }}.</span> {{ step.title }}
            </p>
            <p class="mt-1 max-w-64 text-sm text-foreground-muted">{{ step.text }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Fleet preview -->
    <section class="bg-page">
      <div class="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        <p v-reveal class="text-center text-sm font-semibold uppercase tracking-widest text-accent">
          Handpicked &amp; well maintained
        </p>
        <h2 v-reveal class="mt-2 text-center font-[Georgia] text-3xl font-bold text-foreground">
          Our Fleet. <span class="text-accent">Comfort for every need.</span>
        </h2>

        <div class="mt-8 grid gap-6 sm:mt-10 sm:grid-cols-2 lg:grid-cols-4">
          <VehicleCard v-for="vehicle in catalog.vehicles.slice(0, 4)" :key="vehicle.id" v-reveal :vehicle="vehicle" />
        </div>

        <div class="mt-8 text-center">
          <RouterLink to="/fleet" class="font-semibold text-accent hover:text-accent-strong">
            View full fleet &rarr;
          </RouterLink>
        </div>
      </div>
    </section>

    <!-- Experience / trust badges -->
    <section class="relative overflow-hidden border-y border-border-subtle bg-surface">
      <!-- Stands in for the flyer's fisherman-at-sunset photo - a warm horizon-glow gradient,
           not a fabricated photo of a real person or place. -->
      <div
        class="pointer-events-none absolute inset-x-0 bottom-0 h-64 bg-linear-to-t from-gold-500/10 via-brand-blue-500/5 to-transparent"
      ></div>
      <div class="pointer-events-none absolute -left-20 top-1/3 h-72 w-72 rounded-full bg-accent-bg/10 blur-3xl"></div>

      <div class="relative mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-14">
        <h2 v-reveal class="text-center font-[Georgia] text-2xl font-bold text-foreground">
          It's not just a journey, <span class="text-accent">it's an experience.</span>
        </h2>
        <div class="mt-8 grid grid-cols-2 gap-x-6 gap-y-8 sm:mt-10 sm:grid-cols-3 sm:gap-8 lg:grid-cols-5">
          <div
            v-for="(badge, index) in trustBadges"
            :key="badge.title"
            v-reveal
            class="flex flex-col items-center text-center transition duration-300 hover:-translate-y-1"
            :class="{ 'col-span-2 sm:col-span-1': index === trustBadges.length - 1 && trustBadges.length % 2 !== 0 }"
          >
            <div
              class="flex h-14 w-14 items-center justify-center rounded-full border border-accent-border/40 bg-page text-accent"
            >
              <svg
                v-if="badge.icon === 'shield'"
                class="h-6 w-6"
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
                v-else-if="badge.icon === 'people'"
                class="h-6 w-6"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                viewBox="0 0 24 24"
              >
                <circle cx="9" cy="8" r="3" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5" />
                <circle cx="17" cy="9" r="2.4" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M15 14.2c2.2.3 4 2 4.5 4.3" />
              </svg>
              <svg
                v-else-if="badge.icon === 'clock'"
                class="h-6 w-6"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                viewBox="0 0 24 24"
              >
                <circle cx="12" cy="12" r="8.5" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 7.5V12l3 2" />
              </svg>
              <svg
                v-else-if="badge.icon === 'heart'"
                class="h-6 w-6"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M12 21s-6.716-4.35-9.428-8.028C.86 10.42 1.02 7.36 3.343 5.6a5.5 5.5 0 0 1 7.657 1.02L12 7.8l1-1.18a5.5 5.5 0 0 1 7.657-1.02c2.323 1.76 2.483 4.82.77 7.372C18.716 16.65 12 21 12 21Z"
                />
              </svg>
              <svg v-else class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <circle cx="12" cy="9" r="5.5" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 9l2 2 4-4" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 13.8L7.5 21l4.5-2.5 4.5 2.5-1.5-7.2" />
              </svg>
            </div>
            <p class="mt-3 font-semibold text-accent">{{ badge.title }}</p>
            <p class="mt-1 text-sm text-foreground-secondary">{{ badge.text }}</p>
          </div>
        </div>

        <div
          v-reveal
          class="mx-auto mt-14 flex max-w-lg flex-col items-center gap-2 rounded-2xl border border-accent-border/30 bg-page/60 px-8 py-6 text-center"
        >
          <svg class="h-7 w-7 text-accent" fill="currentColor" viewBox="0 0 24 24">
            <path d="M4 18h16v2H4v-2ZM4 8l3.5 2.5L12 5l4.5 5.5L20 8v8H4V8Z" />
          </svg>
          <p class="font-[Georgia] text-lg font-bold text-foreground">
            Your Comfort. <span class="text-accent">Our Commitment.</span>
          </p>
          <p class="font-[Georgia] text-base italic text-foreground-secondary">Karibu sana!</p>
        </div>
      </div>
    </section>

    <!-- Become a driver CTA (hidden once you're already an active driver-partner) -->
    <section v-if="auth.user?.driver_status !== 'active'" class="bg-page">
      <div class="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        <div
          v-reveal
          class="flex flex-col items-center justify-between gap-6 rounded-2xl border border-border-subtle bg-surface px-6 py-10 text-center sm:px-12 md:flex-row md:text-left"
        >
          <div>
            <h2 class="font-[Georgia] text-2xl font-bold text-foreground">
              Own a car? <span class="text-accent">Partner with SilverLake.</span>
            </h2>
            <p class="mt-2 max-w-xl text-sm text-foreground-secondary">
              List your vehicle with us and start earning as a driver-partner. Applications are reviewed by our team
              before you go live.
            </p>
          </div>
          <p
            v-if="auth.user?.driver_status === 'suspended'"
            class="shrink-0 rounded-md border border-danger-border px-6 py-3 font-semibold text-danger"
          >
            Currently Suspended
          </p>
          <RouterLink
            v-else
            to="/become-a-driver"
            class="shrink-0 rounded-md bg-accent-bg px-6 py-3 font-semibold text-on-accent transition hover:bg-accent-bg-hover"
          >
            Become a Driver
          </RouterLink>
        </div>
      </div>
    </section>

    <!-- Reviews preview -->
    <section class="bg-page">
      <div class="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        <p
          v-if="averageRating"
          v-reveal
          class="text-center text-sm font-semibold uppercase tracking-widest text-accent"
        >
          {{ averageRating }}&#9733; average &middot; real reviews from real trips
        </p>
        <h2 v-reveal class="mt-2 text-center font-[Georgia] text-3xl font-bold text-foreground">What our clients say</h2>
        <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <ReviewCard v-for="review in catalog.reviews.slice(0, 3)" :key="review.id" v-reveal :review="review" />
        </div>
        <div class="mt-8 text-center">
          <RouterLink to="/reviews" class="font-semibold text-accent hover:text-accent-strong">
            Read all reviews &rarr;
          </RouterLink>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.hero-fade-enter-active,
.hero-fade-leave-active {
  transition: opacity 0.7s ease;
}
.hero-fade-enter-from,
.hero-fade-leave-to {
  opacity: 0;
}
</style>
