<script setup>
import { computed, onMounted, ref } from 'vue'

import { useCatalogStore } from '../stores/catalog'
import VehicleCard from '../components/VehicleCard.vue'

const catalog = useCatalogStore()
const activeCategory = ref('all')

const categories = computed(() => [
  { value: 'all', label: 'All' },
  ...catalog.categories.map((c) => ({ value: c.slug, label: c.name })),
])

const filteredVehicles = computed(() => {
  if (activeCategory.value === 'all') return catalog.vehicles
  return catalog.vehicles.filter((v) => v.category === activeCategory.value)
})

onMounted(() => {
  catalog.fetchVehicles()
  catalog.fetchCategories()
})
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <h1 class="text-center font-[Georgia] text-3xl font-bold text-navy-900">Our Fleet</h1>
      <p class="mt-2 text-center text-slate-600">Comfort for every need, available with a driver or self drive.</p>

      <div class="mt-8 flex flex-wrap justify-center gap-2">
        <button
          v-for="cat in categories"
          :key="cat.value"
          class="rounded-full border px-4 py-1.5 text-sm font-medium transition"
          :class="
            activeCategory === cat.value
              ? 'border-brand-blue-600 bg-brand-blue-600 text-white'
              : 'border-slate-300 text-slate-600 hover:border-brand-blue-500 hover:text-brand-blue-600'
          "
          @click="activeCategory = cat.value"
        >
          {{ cat.label }}
        </button>
      </div>

      <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <VehicleCard v-for="vehicle in filteredVehicles" :key="vehicle.id" v-reveal :vehicle="vehicle" />
      </div>

      <p v-if="!filteredVehicles.length" class="mt-10 text-center text-slate-500">
        No vehicles in this category yet.
      </p>
    </div>
  </div>
</template>
