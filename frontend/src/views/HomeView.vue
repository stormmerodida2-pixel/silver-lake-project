<script setup>
import { computed, onMounted } from 'vue'

import { useAuthStore } from '../stores/auth'
import { useCatalogStore } from '../stores/catalog'
import KenyaMap from '../components/KenyaMap.vue'
import VehicleCard from '../components/VehicleCard.vue'
import ReviewCard from '../components/ReviewCard.vue'

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
  catalog.vehicles.reduce((sum, vehicle) => sum + (vehicle.trips_completed || 0), 0)
)
const averageRating = computed(() => {
  if (!catalog.reviews.length) return null
  const total = catalog.reviews.reduce((sum, review) => sum + review.rating, 0)
  return (total / catalog.reviews.length).toFixed(1)
})
// The most-traveled photographed vehicle - a genuine "this is our most popular ride" rather
// than an arbitrary first-in-list pick.
const photographedVehiclesByPopularity = computed(() =>
  [...catalog.vehicles.filter((vehicle) => vehicle.image)].sort(
    (a, b) => (b.trips_completed || 0) - (a.trips_completed || 0)
  )
)
const featuredVehicle = computed(() => photographedVehiclesByPopularity.value[0] || null)
// A second real fleet photo peeking from behind the featured one, for a bit of the flyer's
// multi-vehicle energy - simply hidden if there's only one photographed vehicle so far.
const secondaryVehicle = computed(() => photographedVehiclesByPopularity.value[1] || null)

const trustBadges = [
  { title: 'Safety', text: 'Your safety is our promise', icon: 'shield' },
  { title: 'People', text: 'Professional, friendly chauffeurs', icon: 'people' },
  { title: 'Punctuality', text: 'On time, every time', icon: 'clock' },
  { title: 'Hospitality', text: 'We treat you like family', icon: 'heart' },
  { title: 'Quality', text: 'Well maintained vehicles', icon: 'badge' },
]

const howItWorks = [
  { title: 'Browse & Choose', text: 'Explore the fleet and pick the vehicle that fits your trip.', icon: 'search' },
  { title: 'Book Your Dates', text: 'Reserve with a 30% deposit via M-Pesa - confirmed instantly.', icon: 'calendar' },
  { title: 'Ride With Confidence', text: 'Meet your chauffeur or grab the keys - we handle the rest.', icon: 'wheel' },
]
</script>

<template>
  <div>
    <!-- Hero -->
    <section class="relative overflow-hidden border-b border-navy-800 bg-linear-to-b from-navy-900 to-navy-950">
      <div class="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-gold-500/10 blur-3xl"></div>
      <div class="pointer-events-none absolute -left-32 bottom-0 h-72 w-72 rounded-full bg-brand-blue-500/10 blur-3xl"></div>

      <div class="relative mx-auto grid max-w-6xl gap-12 px-4 py-20 sm:px-6 sm:py-28 lg:grid-cols-2 lg:items-center">
        <div>
          <p class="text-sm font-semibold uppercase tracking-widest text-gold-400">Kisumu &bull; Across Kenya</p>
          <h1 class="mt-3 max-w-2xl font-[Georgia] text-4xl font-bold leading-tight text-white sm:text-5xl">
            We don't just move you,
            <span class="text-gold-400">we elevate your journey.</span>
          </h1>
          <p class="mt-5 max-w-xl text-slate-300">
            From the shores of Lake Victoria to every destination in Kenya, we deliver comfort, class and care in
            every mile.
          </p>

          <div class="mt-8 flex flex-wrap gap-4">
            <RouterLink
              to="/book?service=with_driver"
              class="rounded-md bg-gold-500 px-6 py-3 font-semibold text-navy-950 transition hover:bg-gold-400"
            >
              Book with Driver
            </RouterLink>
            <RouterLink
              to="/book?service=self_drive"
              class="rounded-md border border-gold-400 px-6 py-3 font-semibold text-gold-400 transition hover:bg-navy-800"
            >
              Self Drive
            </RouterLink>
          </div>

          <dl
            v-if="catalog.vehicles.length || totalTripsCompleted > 0 || averageRating"
            class="mt-10 flex flex-wrap gap-x-10 gap-y-4 border-t border-navy-800 pt-6"
          >
            <div v-if="catalog.vehicles.length">
              <dt class="font-[Georgia] text-2xl font-bold text-white">{{ catalog.vehicles.length }}+</dt>
              <dd class="text-xs uppercase tracking-wide text-slate-400">Vehicles in the fleet</dd>
            </div>
            <div v-if="totalTripsCompleted > 0">
              <dt class="font-[Georgia] text-2xl font-bold text-white">{{ totalTripsCompleted }}+</dt>
              <dd class="text-xs uppercase tracking-wide text-slate-400">Trips completed</dd>
            </div>
            <div v-if="averageRating">
              <dt class="font-[Georgia] text-2xl font-bold text-white">{{ averageRating }}<span class="text-gold-400">&#9733;</span></dt>
              <dd class="text-xs uppercase tracking-wide text-slate-400">Average rating</dd>
            </div>
          </dl>
        </div>

        <div v-if="featuredVehicle" v-reveal class="relative mx-auto hidden w-full max-w-md lg:block">
          <!-- Stands in for the flyer's Lake Victoria sunset backdrop - a warm gradient glow,
               not a fabricated photo, behind the real fleet photography below. -->
          <div class="absolute -inset-8 rounded-[2.5rem] bg-linear-to-br from-gold-500/25 via-brand-blue-500/10 to-transparent blur-2xl"></div>

          <div
            v-if="secondaryVehicle"
            class="absolute -right-8 -top-8 hidden w-36 rotate-6 overflow-hidden rounded-xl border border-navy-700 shadow-xl shadow-black/40 sm:block"
          >
            <img :src="secondaryVehicle.image" :alt="secondaryVehicle.name" class="h-24 w-full object-cover" />
          </div>

          <div class="absolute inset-4 rounded-2xl border-2 border-gold-400/30"></div>
          <div class="relative overflow-hidden rounded-2xl border border-navy-700 shadow-2xl shadow-black/40">
            <img
              :src="featuredVehicle.image"
              :alt="featuredVehicle.name"
              class="h-80 w-full object-cover"
            />
            <div class="absolute inset-x-0 bottom-0 bg-linear-to-t from-navy-950/95 to-transparent p-5 pt-10">
              <p class="font-[Georgia] text-lg font-bold text-white">{{ featuredVehicle.name }}</p>
              <p class="text-sm text-gold-400">{{ featuredVehicle.category_name || featuredVehicle.category }}</p>
            </div>
            <span
              v-if="featuredVehicle.trips_completed > 0"
              class="absolute right-3 top-3 rounded-full bg-navy-950/80 px-2.5 py-1 text-xs font-semibold text-gold-400 backdrop-blur"
            >
              Most popular ride
            </span>
          </div>
        </div>
      </div>

      <svg class="absolute inset-x-0 -bottom-1 h-10 w-full text-navy-900" viewBox="0 0 1440 60" preserveAspectRatio="none" fill="currentColor" aria-hidden="true">
        <path d="M0,32 C240,60 480,0 720,20 C960,40 1200,10 1440,30 L1440,60 L0,60 Z" />
      </svg>
    </section>

    <!-- Rooted in Kisumu banner -->
    <section v-reveal class="border-b border-navy-800 bg-navy-900">
      <div class="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-2">
        <div class="flex items-start gap-5">
          <div class="hidden h-20 w-20 shrink-0 sm:block">
            <KenyaMap mode="origin" />
          </div>
          <div>
            <h2 class="font-[Georgia] text-2xl font-bold text-white">
              Rooted in Kisumu. <span class="text-gold-400">Driven across Kenya.</span>
            </h2>
            <p class="mt-2 text-sm text-slate-300">
              We are more than a car hire company. We are your travel partners. Anywhere. Anytime.
            </p>
          </div>
        </div>
        <ul class="flex flex-col justify-center gap-4 text-sm text-slate-200">
          <li class="flex items-center gap-3">
            <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-gold-400/40 bg-navy-950 text-gold-400">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 21s6-5.2 6-10.5A6 6 0 0 0 6 10.5C6 15.8 12 21 12 21Z" />
                <circle cx="12" cy="10.5" r="2.2" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
            Local Expertise
          </li>
          <li class="flex items-center gap-3">
            <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-gold-400/40 bg-navy-950 text-gold-400">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M3 17l4-7 3 4 3-6 5 9" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M3 20h18" />
              </svg>
            </span>
            National Reach
          </li>
          <li class="flex items-center gap-3">
            <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-gold-400/40 bg-navy-950 text-gold-400">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path d="M12 21s-6.716-4.35-9.428-8.028C.86 10.42 1.02 7.36 3.343 5.6a5.5 5.5 0 0 1 7.657 1.02L12 7.8l1-1.18a5.5 5.5 0 0 1 7.657-1.02c2.323 1.76 2.483 4.82.77 7.372C18.716 16.65 12 21 12 21Z" />
              </svg>
            </span>
            Personal Touch
          </li>
        </ul>
      </div>
    </section>

    <!-- How it works -->
    <section v-reveal class="bg-white">
      <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <p class="text-center text-sm font-semibold uppercase tracking-widest text-brand-blue-600">
          Simple, from booking to ride
        </p>
        <h2 class="mt-2 text-center font-[Georgia] text-3xl font-bold text-navy-900">How It Works</h2>

        <div class="relative mt-14 grid gap-10 sm:grid-cols-3">
          <div class="absolute left-[16.5%] right-[16.5%] top-8 hidden h-px bg-slate-200 sm:block"></div>

          <div v-for="(step, index) in howItWorks" :key="step.title" class="relative flex flex-col items-center text-center">
            <div class="relative z-10 flex h-16 w-16 items-center justify-center rounded-full border-2 border-gold-400 bg-navy-900 text-gold-400">
              <svg v-if="step.icon === 'search'" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <circle cx="10.5" cy="10.5" r="6.5" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M20 20l-4.35-4.35" />
              </svg>
              <svg v-else-if="step.icon === 'calendar'" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <rect x="4" y="5" width="16" height="15" rx="2" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 10h16M8 3v4M16 3v4" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 14.5l2 2 4-4.5" />
              </svg>
              <svg v-else class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="8.5" stroke-linecap="round" stroke-linejoin="round" />
                <circle cx="12" cy="12" r="2" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 5.5v4M6.3 15.3l3.2-2.2M17.7 15.3l-3.2-2.2" />
              </svg>
            </div>
            <p class="mt-5 font-[Georgia] text-lg font-bold text-navy-900">
              <span class="text-gold-500">{{ String(index + 1).padStart(2, '0') }}.</span> {{ step.title }}
            </p>
            <p class="mt-1 max-w-64 text-sm text-slate-600">{{ step.text }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Fleet preview -->
    <section class="bg-slate-50">
      <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <p v-reveal class="text-center text-sm font-semibold uppercase tracking-widest text-brand-blue-600">
          Handpicked &amp; well maintained
        </p>
        <h2 v-reveal class="mt-2 text-center font-[Georgia] text-3xl font-bold text-navy-900">
          Our Fleet. <span class="text-brand-blue-600">Comfort for every need.</span>
        </h2>

        <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <VehicleCard v-for="vehicle in catalog.vehicles.slice(0, 4)" :key="vehicle.id" v-reveal :vehicle="vehicle" />
        </div>

        <div class="mt-8 text-center">
          <RouterLink to="/fleet" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500">
            View full fleet &rarr;
          </RouterLink>
        </div>
      </div>
    </section>

    <!-- Experience / trust badges -->
    <section class="relative overflow-hidden border-y border-navy-800 bg-navy-900">
      <!-- Stands in for the flyer's fisherman-at-sunset photo - a warm horizon-glow gradient,
           not a fabricated photo of a real person or place. -->
      <div class="pointer-events-none absolute inset-x-0 bottom-0 h-64 bg-linear-to-t from-gold-500/10 via-brand-blue-500/5 to-transparent"></div>
      <div class="pointer-events-none absolute -left-20 top-1/3 h-72 w-72 rounded-full bg-gold-500/10 blur-3xl"></div>

      <div class="relative mx-auto max-w-6xl px-4 py-14 sm:px-6">
        <h2 v-reveal class="text-center font-[Georgia] text-2xl font-bold text-white">
          It's not just a journey, <span class="text-gold-400">it's an experience.</span>
        </h2>
        <div class="mt-10 grid gap-8 sm:grid-cols-3 lg:grid-cols-5">
          <div v-for="badge in trustBadges" :key="badge.title" v-reveal class="flex flex-col items-center text-center transition duration-300 hover:-translate-y-1">
            <div class="flex h-14 w-14 items-center justify-center rounded-full border border-gold-400/40 bg-navy-950 text-gold-400">
              <svg v-if="badge.icon === 'shield'" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 3.5l6.5 2.5v4.8c0 4.6-2.9 8-6.5 9.7-3.6-1.7-6.5-5.1-6.5-9.7V6l6.5-2.5z" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.3l2 2 4.5-4.5" />
              </svg>
              <svg v-else-if="badge.icon === 'people'" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <circle cx="9" cy="8" r="3" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5" />
                <circle cx="17" cy="9" r="2.4" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M15 14.2c2.2.3 4 2 4.5 4.3" />
              </svg>
              <svg v-else-if="badge.icon === 'clock'" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="8.5" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 7.5V12l3 2" />
              </svg>
              <svg v-else-if="badge.icon === 'heart'" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 21s-6.716-4.35-9.428-8.028C.86 10.42 1.02 7.36 3.343 5.6a5.5 5.5 0 0 1 7.657 1.02L12 7.8l1-1.18a5.5 5.5 0 0 1 7.657-1.02c2.323 1.76 2.483 4.82.77 7.372C18.716 16.65 12 21 12 21Z" />
              </svg>
              <svg v-else class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <circle cx="12" cy="9" r="5.5" stroke-linecap="round" stroke-linejoin="round" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 9l2 2 4-4" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 13.8L7.5 21l4.5-2.5 4.5 2.5-1.5-7.2" />
              </svg>
            </div>
            <p class="mt-3 font-semibold text-gold-400">{{ badge.title }}</p>
            <p class="mt-1 text-sm text-slate-300">{{ badge.text }}</p>
          </div>
        </div>

        <div v-reveal class="mx-auto mt-14 flex max-w-lg flex-col items-center gap-2 rounded-2xl border border-gold-400/30 bg-navy-950/60 px-8 py-6 text-center">
          <svg class="h-7 w-7 text-gold-400" fill="currentColor" viewBox="0 0 24 24">
            <path d="M4 18h16v2H4v-2ZM4 8l3.5 2.5L12 5l4.5 5.5L20 8v8H4V8Z" />
          </svg>
          <p class="font-[Georgia] text-lg font-bold text-white">
            Your Comfort. <span class="text-gold-400">Our Commitment.</span>
          </p>
          <p class="font-[Georgia] text-base italic text-slate-300">Karibu sana!</p>
        </div>
      </div>
    </section>

    <!-- Become a driver CTA (hidden once you're already an active driver-partner) -->
    <section v-if="auth.user?.driver_status !== 'active'" class="bg-white">
      <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div v-reveal class="flex flex-col items-center justify-between gap-6 rounded-2xl border border-navy-800 bg-navy-900 px-6 py-10 text-center sm:px-12 md:flex-row md:text-left">
          <div>
            <h2 class="font-[Georgia] text-2xl font-bold text-white">
              Own a car? <span class="text-gold-400">Partner with SilverLake.</span>
            </h2>
            <p class="mt-2 max-w-xl text-sm text-slate-300">
              List your vehicle with us and start earning as a driver-partner. Applications are reviewed
              by our team before you go live.
            </p>
          </div>
          <p
            v-if="auth.user?.driver_status === 'suspended'"
            class="shrink-0 rounded-md border border-red-400 px-6 py-3 font-semibold text-red-400"
          >
            Currently Suspended
          </p>
          <RouterLink
            v-else
            to="/become-a-driver"
            class="shrink-0 rounded-md bg-gold-500 px-6 py-3 font-semibold text-navy-950 transition hover:bg-gold-400"
          >
            Become a Driver
          </RouterLink>
        </div>
      </div>
    </section>

    <!-- Reviews preview -->
    <section class="bg-white">
      <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <p v-if="averageRating" v-reveal class="text-center text-sm font-semibold uppercase tracking-widest text-brand-blue-600">
          {{ averageRating }}&#9733; average &middot; real reviews from real trips
        </p>
        <h2 v-reveal class="mt-2 text-center font-[Georgia] text-3xl font-bold text-navy-900">What our clients say</h2>
        <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <ReviewCard v-for="review in catalog.reviews.slice(0, 3)" :key="review.id" v-reveal :review="review" />
        </div>
        <div class="mt-8 text-center">
          <RouterLink to="/reviews" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500">
            Read all reviews &rarr;
          </RouterLink>
        </div>
      </div>
    </section>
  </div>
</template>
