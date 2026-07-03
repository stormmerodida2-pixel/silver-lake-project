<script setup>
import { computed, onMounted, ref } from 'vue'

import { useCatalogStore } from '../stores/catalog'
import VehicleCard from '../components/VehicleCard.vue'

const catalog = useCatalogStore()
const activeCategory = ref('all')

const categories = [
  { value: 'all', label: 'All' },
  { value: 'executive_suv', label: 'Executive SUV' },
  { value: 'premium_mpv', label: 'Premium MPV' },
  { value: 'compact_sedan', label: 'Compact Sedan' },
  { value: 'passenger_van', label: 'Passenger Van' },
]

const filteredVehicles = computed(() => {
  if (activeCategory.value === 'all') return catalog.vehicles
  return catalog.vehicles.filter((v) => v.category === activeCategory.value)
})

onMounted(() => {
  catalog.fetchVehicles()
})
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
    <h1 class="text-center font-[Georgia] text-3xl font-bold text-white">Our Fleet</h1>
    <p class="mt-2 text-center text-slate-400">Comfort for every need, available with a driver or self drive.</p>

    <div class="mt-8 flex flex-wrap justify-center gap-2">
      <button
        v-for="cat in categories"
        :key="cat.value"
        class="rounded-full border px-4 py-1.5 text-sm font-medium transition"
        :class="
          activeCategory === cat.value
            ? 'border-gold-500 bg-gold-500 text-navy-950'
            : 'border-navy-700 text-slate-300 hover:border-gold-400 hover:text-gold-400'
        "
        @click="activeCategory = cat.value"
      >
        {{ cat.label }}
      </button>
    </div>

    <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
      <VehicleCard v-for="vehicle in filteredVehicles" :key="vehicle.id" :vehicle="vehicle" />
    </div>

    <p v-if="!filteredVehicles.length" class="mt-10 text-center text-slate-400">
      No vehicles in this category yet.
    </p>
  </div>
</template>
