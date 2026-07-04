<script setup>
import { onMounted } from 'vue'

import { useCatalogStore } from '../stores/catalog'
import VehicleCard from '../components/VehicleCard.vue'
import ReviewCard from '../components/ReviewCard.vue'

const catalog = useCatalogStore()

onMounted(() => {
  catalog.fetchVehicles()
  catalog.fetchReviews()
})

const trustBadges = [
  { title: 'Safety', text: 'Your safety is our promise' },
  { title: 'People', text: 'Professional, friendly chauffeurs' },
  { title: 'Punctuality', text: 'On time, every time' },
  { title: 'Hospitality', text: 'We treat you like family' },
  { title: 'Quality', text: 'Well maintained vehicles' },
]
</script>

<template>
  <div>
    <!-- Hero -->
    <section class="relative overflow-hidden border-b border-navy-800 bg-linear-to-b from-navy-900 to-navy-950">
      <div class="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28">
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
      </div>
    </section>

    <!-- Rooted in Kisumu banner -->
    <section class="border-b border-navy-800 bg-navy-900">
      <div class="mx-auto grid max-w-6xl gap-6 px-4 py-8 sm:px-6 md:grid-cols-2">
        <div>
          <h2 class="font-[Georgia] text-2xl font-bold text-white">
            Rooted in Kisumu. <span class="text-gold-400">Driven across Kenya.</span>
          </h2>
          <p class="mt-2 text-sm text-slate-300">
            We are more than a car hire company. We are your travel partners. Anywhere. Anytime.
          </p>
        </div>
        <ul class="flex flex-col justify-center gap-2 text-sm text-slate-200">
          <li class="flex items-center gap-2"><span class="text-gold-400">&check;</span> Local Expertise</li>
          <li class="flex items-center gap-2"><span class="text-gold-400">&check;</span> National Reach</li>
          <li class="flex items-center gap-2"><span class="text-gold-400">&check;</span> Personal Touch</li>
        </ul>
      </div>
    </section>

    <!-- Fleet preview -->
    <section class="bg-white">
      <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <h2 class="text-center font-[Georgia] text-3xl font-bold text-navy-900">
          Our Fleet. <span class="text-brand-blue-600">Comfort for every need.</span>
        </h2>

        <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <VehicleCard v-for="vehicle in catalog.vehicles.slice(0, 4)" :key="vehicle.id" :vehicle="vehicle" />
        </div>

        <div class="mt-8 text-center">
          <RouterLink to="/fleet" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500">
            View full fleet &rarr;
          </RouterLink>
        </div>
      </div>
    </section>

    <!-- Experience / trust badges -->
    <section class="border-y border-navy-800 bg-navy-900">
      <div class="mx-auto max-w-6xl px-4 py-14 sm:px-6">
        <h2 class="text-center font-[Georgia] text-2xl font-bold text-white">
          It's not just a journey, <span class="text-gold-400">it's an experience.</span>
        </h2>
        <div class="mt-8 grid gap-6 sm:grid-cols-3 lg:grid-cols-5">
          <div v-for="badge in trustBadges" :key="badge.title" class="text-center">
            <p class="font-semibold text-gold-400">{{ badge.title }}</p>
            <p class="mt-1 text-sm text-slate-300">{{ badge.text }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Reviews preview -->
    <section class="bg-white">
      <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <h2 class="text-center font-[Georgia] text-3xl font-bold text-navy-900">What our clients say</h2>
        <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <ReviewCard v-for="review in catalog.reviews.slice(0, 3)" :key="review.id" :review="review" />
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
