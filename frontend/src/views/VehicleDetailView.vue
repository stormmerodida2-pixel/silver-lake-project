<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import apiClient from '../api/client'
import { useCatalogStore } from '../stores/catalog'

const route = useRoute()
const router = useRouter()
const catalog = useCatalogStore()

const vehicle = ref(null)
const loading = ref(true)
const error = ref('')

const categoryLabels = {
  executive_suv: 'Executive SUV',
  premium_mpv: 'Premium MPV',
  compact_sedan: 'Compact Sedan',
  passenger_van: 'Passenger Van',
}

onMounted(async () => {
  // Try catalog cache first, fall back to direct API call
  await catalog.fetchVehicles()
  const cached = catalog.vehicles.find((v) => v.id === Number(route.params.id))
  if (cached) {
    vehicle.value = cached
    loading.value = false
    return
  }
  try {
    const { data } = await apiClient.get(`/fleet/vehicles/${route.params.id}/`)
    vehicle.value = data
  } catch (err) {
    if (err.response?.status === 404) {
      router.replace('/fleet')
    } else {
      error.value = 'Could not load vehicle details.'
    }
  } finally {
    loading.value = false
  }
})

const selfDriveUrl = computed(() => `/book?vehicle=${vehicle.value?.id}&service=self_drive`)
const withDriverUrl = computed(() => `/book?vehicle=${vehicle.value?.id}&service=with_driver`)
</script>

<template>
  <div class="bg-white">
    <p v-if="loading" class="py-32 text-center text-slate-500">Loading...</p>
    <p v-else-if="error" class="py-32 text-center text-red-600">{{ error }}</p>

    <template v-else-if="vehicle">
      <!-- Hero image -->
      <div class="relative h-72 w-full bg-slate-100 sm:h-96">
        <img
          v-if="vehicle.image"
          :src="vehicle.image"
          :alt="vehicle.name"
          class="h-full w-full object-cover"
        />
        <div v-else class="flex h-full items-center justify-center text-slate-300 text-lg">No photo available</div>
        <!-- Back link -->
        <RouterLink
          to="/fleet"
          class="absolute top-4 left-4 flex items-center gap-1.5 rounded-full bg-white/90 px-4 py-2 text-sm font-semibold text-navy-900 shadow backdrop-blur hover:bg-white"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          All Vehicles
        </RouterLink>
      </div>

      <div class="mx-auto max-w-5xl px-4 py-12 sm:px-6">
        <div class="grid gap-10 lg:grid-cols-3">

          <!-- Left: details -->
          <div class="lg:col-span-2">
            <p class="text-sm font-semibold uppercase tracking-widest text-brand-blue-600">
              {{ categoryLabels[vehicle.category] || vehicle.category }}
            </p>
            <h1 class="mt-2 font-[Georgia] text-3xl font-bold text-navy-900 sm:text-4xl">
              {{ vehicle.name }}
            </h1>
            <p v-if="vehicle.tagline" class="mt-2 text-lg text-slate-500 italic">{{ vehicle.tagline }}</p>

            <!-- Specs grid -->
            <div class="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3">
              <div class="rounded-xl border border-slate-200 bg-slate-50 p-4 text-center">
                <p class="text-2xl font-bold text-navy-900">{{ vehicle.passenger_capacity }}</p>
                <p class="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">Passengers</p>
              </div>
              <div class="rounded-xl border border-slate-200 bg-slate-50 p-4 text-center">
                <p class="text-2xl font-bold text-gold-600">
                  KES {{ Number(vehicle.price_per_day).toLocaleString() }}
                </p>
                <p class="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">Per Day</p>
              </div>
              <div class="rounded-xl border border-slate-200 bg-slate-50 p-4 text-center col-span-2 sm:col-span-1">
                <p class="text-sm font-semibold text-navy-900 mt-1">
                  <span v-if="vehicle.allow_with_driver && vehicle.allow_self_drive">With Driver &amp; Self Drive</span>
                  <span v-else-if="vehicle.allow_with_driver">With Driver Only</span>
                  <span v-else>Self Drive Only</span>
                </p>
                <p class="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">Service Type</p>
              </div>
            </div>

            <div v-if="vehicle.description" class="mt-8">
              <h2 class="font-[Georgia] text-xl font-bold text-navy-900">About This Vehicle</h2>
              <p class="mt-3 leading-relaxed text-slate-600">{{ vehicle.description }}</p>
            </div>

            <!-- Gallery -->
            <div v-if="vehicle.gallery_images?.length" class="mt-8">
              <h2 class="font-[Georgia] text-xl font-bold text-navy-900">Gallery</h2>
              <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
                <img
                  v-for="img in vehicle.gallery_images"
                  :key="img.id"
                  :src="img.image"
                  :alt="img.caption || vehicle.name"
                  class="aspect-4/3 w-full rounded-lg object-cover"
                />
              </div>
            </div>
          </div>

          <!-- Right: booking CTA -->
          <div class="lg:col-span-1">
            <div class="sticky top-6 rounded-2xl border border-slate-200 bg-slate-50 p-6 shadow-lg">
              <p class="text-center text-2xl font-bold text-navy-900">
                KES {{ Number(vehicle.price_per_day).toLocaleString() }}
                <span class="text-sm font-normal text-slate-500">/day</span>
              </p>
              <p class="mt-1 text-center text-xs text-slate-500">30% deposit required to confirm</p>

              <div class="mt-6 space-y-3">
                <RouterLink
                  v-if="vehicle.allow_with_driver"
                  :to="withDriverUrl"
                  class="flex w-full items-center justify-center rounded-xl bg-gold-500 py-3 font-semibold text-navy-950 transition hover:bg-gold-400"
                >
                  Book with Driver
                </RouterLink>
                <RouterLink
                  v-if="vehicle.allow_self_drive"
                  :to="selfDriveUrl"
                  class="flex w-full items-center justify-center rounded-xl border border-navy-900 py-3 font-semibold text-navy-900 transition hover:bg-navy-900 hover:text-white"
                >
                  Self Drive
                </RouterLink>
              </div>

              <p class="mt-5 text-center text-xs text-slate-500">
                Need help?
                <a href="tel:+254790111000" class="font-semibold text-brand-blue-600 hover:underline">
                  Call 0790 111 000
                </a>
              </p>
            </div>
          </div>

        </div>
      </div>
    </template>
  </div>
</template>
