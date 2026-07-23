<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import apiClient from '../api/client'
import { useCatalogStore } from '../stores/catalog'
import VehicleCard from '../components/VehicleCard.vue'

const catalog = useCatalogStore()
const activeCategory = ref('all')
const todayString = new Date().toISOString().split('T')[0]

const categories = computed(() => [
  { value: 'all', label: 'All' },
  ...catalog.categories.map((c) => ({ value: c.slug, label: c.name })),
])

// ── Date-first search ────────────────────────────────────────────────────
// Filters the listing down to vehicles actually free for the whole requested range, instead
// of a customer discovering a conflict only after picking a vehicle and filling out the whole
// booking form. `null` here (not just empty dates) distinguishes "no search run yet" from "ran
// a search and nothing was available".
const dateFilter = reactive({ start_date: '', end_date: '' })
const dateFilteredVehicles = ref(null)
const dateFilterLoading = ref(false)
const dateFilterError = ref('')
const isDateFilterActive = computed(() => dateFilteredVehicles.value !== null)

async function checkAvailability() {
  if (!dateFilter.start_date || !dateFilter.end_date) return
  dateFilterLoading.value = true
  dateFilterError.value = ''
  try {
    const { data } = await apiClient.get('/vehicles/', { params: dateFilter })
    dateFilteredVehicles.value = data.results ?? data
  } catch {
    dateFilterError.value = 'Could not check availability for those dates.'
  } finally {
    dateFilterLoading.value = false
  }
}

function clearDateFilter() {
  dateFilter.start_date = ''
  dateFilter.end_date = ''
  dateFilteredVehicles.value = null
  dateFilterError.value = ''
}

const baseVehicles = computed(() => dateFilteredVehicles.value ?? catalog.vehicles)
const filteredVehicles = computed(() => {
  if (activeCategory.value === 'all') return baseVehicles.value
  return baseVehicles.value.filter((v) => v.category === activeCategory.value)
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

      <div
        class="mx-auto mt-8 flex max-w-2xl flex-wrap items-end justify-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4"
      >
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Pickup date</label>
          <input
            v-model="dateFilter.start_date"
            type="date"
            :min="todayString"
            class="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-navy-900 focus:border-brand-blue-500 focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-600">Return date</label>
          <input
            v-model="dateFilter.end_date"
            type="date"
            :min="dateFilter.start_date || todayString"
            class="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-navy-900 focus:border-brand-blue-500 focus:outline-none"
          />
        </div>
        <button
          type="button"
          :disabled="!dateFilter.start_date || !dateFilter.end_date || dateFilterLoading"
          class="rounded-md bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition hover:bg-gold-400 disabled:cursor-not-allowed disabled:opacity-50"
          @click="checkAvailability"
        >
          {{ dateFilterLoading ? 'Checking...' : 'Check Availability' }}
        </button>
        <button
          v-if="isDateFilterActive"
          type="button"
          class="rounded-md px-3 py-2 text-sm font-semibold text-slate-500 transition hover:text-navy-900"
          @click="clearDateFilter"
        >
          Clear
        </button>
      </div>
      <p v-if="dateFilterError" class="mt-3 text-center text-sm text-red-600">{{ dateFilterError }}</p>
      <p v-else-if="isDateFilterActive" class="mt-3 text-center text-sm text-slate-500">
        Showing vehicles available {{ dateFilter.start_date }} to {{ dateFilter.end_date }}.
      </p>

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
        {{ isDateFilterActive ? 'No vehicles are available for those dates.' : 'No vehicles in this category yet.' }}
      </p>
    </div>
  </div>
</template>
