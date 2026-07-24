<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../api/client'

const props = defineProps({
  bookingId: { type: [Number, String], required: true },
})

const loading = ref(true)
const error = ref('')
const reports = ref([])

const fuelLevelLabels = {
  empty: 'Empty',
  quarter: '1/4',
  half: '1/2',
  three_quarters: '3/4',
  full: 'Full',
}

function reportFor(type) {
  return reports.value.find((report) => report.report_type === type)
}

async function load() {
  error.value = ''
  try {
    const { data } = await apiClient.get(`/bookings/${props.bookingId}/condition-reports/`)
    reports.value = data
  } catch {
    error.value = 'Could not load the vehicle condition report.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="rounded-lg border border-slate-200 bg-white p-4">
    <p v-if="loading" class="text-sm text-slate-500">Loading vehicle condition report...</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>
    <p v-else-if="!reports.length" class="text-sm text-slate-500">
      No condition report has been logged for this trip yet.
    </p>
    <div v-else class="grid gap-4 sm:grid-cols-2">
      <div v-for="type in ['pickup', 'return']" :key="type">
        <template v-if="reportFor(type)">
          <p class="text-sm font-semibold uppercase tracking-wide text-slate-700">
            {{ type === 'pickup' ? 'At Pickup' : 'At Return' }}
          </p>
          <div class="mt-2 space-y-1 text-sm text-slate-600">
            <p v-if="reportFor(type).mileage">Odometer: {{ Number(reportFor(type).mileage).toLocaleString() }} km</p>
            <p v-if="reportFor(type).fuel_level">Fuel: {{ fuelLevelLabels[reportFor(type).fuel_level] }}</p>
            <p v-if="reportFor(type).notes">{{ reportFor(type).notes }}</p>
          </div>
          <div v-if="reportFor(type).photos.length" class="mt-2 flex flex-wrap gap-2">
            <a
              v-for="photo in reportFor(type).photos"
              :key="photo.id"
              :href="photo.image"
              target="_blank"
              rel="noopener"
            >
              <img
                :src="photo.image"
                alt="Vehicle condition photo"
                class="h-20 w-28 rounded-md border border-slate-200 object-cover"
              />
            </a>
          </div>
        </template>
        <p v-else class="text-sm text-slate-400">
          {{ type === 'pickup' ? 'Pickup' : 'Return' }} condition not yet logged.
        </p>
      </div>
    </div>
  </div>
</template>
