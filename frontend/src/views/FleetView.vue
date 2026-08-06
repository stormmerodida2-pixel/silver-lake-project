<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import apiClient from '../api/client'
import { useCatalogStore } from '../stores/catalog'
import VehicleCard from '../components/VehicleCard.vue'

const catalog = useCatalogStore()
const route = useRoute()
const router = useRouter()
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
const dateFilter = reactive({
  start_date: typeof route.query.start_date === 'string' ? route.query.start_date : '',
  end_date: typeof route.query.end_date === 'string' ? route.query.end_date : '',
})
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
    // Keeps the URL shareable/bookmarkable, and is what lets a vehicle's detail-page CTA
    // carry these dates forward into the booking form instead of the customer re-typing them.
    router.replace({ query: { start_date: dateFilter.start_date, end_date: dateFilter.end_date } })
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
  router.replace({ query: {} })
}

const baseVehicles = computed(() => dateFilteredVehicles.value ?? catalog.vehicles)
const filteredVehicles = computed(() => {
  if (activeCategory.value === 'all') return baseVehicles.value
  return baseVehicles.value.filter((v) => v.category === activeCategory.value)
})

onMounted(() => {
  catalog.fetchVehicles()
  catalog.fetchCategories()
  if (dateFilter.start_date && dateFilter.end_date) checkAvailability()
})
</script>

<template>
  <div class="bg-page">
    <div class="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
      <p class="text-center text-sm font-semibold uppercase tracking-widest text-accent">Select Your Car</p>
      <h1 class="mt-2 text-center font-[Georgia] text-3xl font-bold text-foreground">Our Fleet</h1>
      <p class="mt-2 text-center text-foreground-muted">Comfort for every need, available with a driver or self drive.</p>

      <div
        class="mx-auto mt-8 flex max-w-2xl flex-wrap items-end justify-center gap-3 rounded-2xl border border-border-subtle bg-surface p-4"
      >
        <div>
          <label class="mb-1 block text-xs font-medium text-foreground-muted">Pickup date</label>
          <input
            v-model="dateFilter.start_date"
            type="date"
            :min="todayString"
            class="rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-foreground [color-scheme:dark] focus:border-accent-border focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-foreground-muted">Return date</label>
          <input
            v-model="dateFilter.end_date"
            type="date"
            :min="dateFilter.start_date || todayString"
            class="rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-foreground [color-scheme:dark] focus:border-accent-border focus:outline-none"
          />
        </div>
        <button
          type="button"
          :disabled="!dateFilter.start_date || !dateFilter.end_date || dateFilterLoading"
          class="rounded-full bg-accent-bg px-5 py-2.5 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
          @click="checkAvailability"
        >
          {{ dateFilterLoading ? 'Checking...' : 'Check Availability' }}
        </button>
        <button
          v-if="isDateFilterActive"
          type="button"
          class="rounded-full px-3 py-2.5 text-sm font-semibold text-foreground-muted transition hover:text-foreground"
          @click="clearDateFilter"
        >
          Clear
        </button>
      </div>
      <p v-if="dateFilterError" class="mt-3 text-center text-sm text-danger">{{ dateFilterError }}</p>
      <p v-else-if="isDateFilterActive" class="mt-3 text-center text-sm text-foreground-muted">
        Showing vehicles available {{ dateFilter.start_date }} to {{ dateFilter.end_date }}.
      </p>

      <div class="mt-8 flex flex-wrap justify-center gap-2">
        <button
          v-for="cat in categories"
          :key="cat.value"
          class="rounded-full px-5 py-2 text-sm font-semibold transition"
          :class="
            activeCategory === cat.value
              ? 'bg-accent-bg text-on-accent shadow-lg shadow-gold-500/20'
              : 'bg-surface text-foreground-secondary hover:bg-surface-2'
          "
          @click="activeCategory = cat.value"
        >
          {{ cat.label }}
        </button>
      </div>

      <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <VehicleCard
          v-for="vehicle in filteredVehicles"
          :key="vehicle.id"
          v-reveal
          :vehicle="vehicle"
          :start-date="dateFilter.start_date"
          :end-date="dateFilter.end_date"
        />
      </div>

      <p v-if="!filteredVehicles.length" class="mt-10 text-center text-foreground-muted">
        {{ isDateFilterActive ? 'No vehicles are available for those dates.' : 'No vehicles in this category yet.' }}
      </p>
    </div>
  </div>
</template>
