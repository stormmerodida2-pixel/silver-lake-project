<script setup>
import { computed, onMounted, ref } from 'vue'

import apiClient from '../api/client'
import { useCatalogStore } from '../stores/catalog'

const catalog = useCatalogStore()
const bookings = ref([])
const loading = ref(true)
const cancellingId = ref(null)
const error = ref('')

const statusStyles = {
  pending: 'text-slate-300',
  confirmed: 'text-gold-400',
  ongoing: 'text-gold-400',
  completed: 'text-slate-400',
  cancelled: 'text-red-400',
}

function vehicleName(id) {
  return catalog.vehicles.find((v) => v.id === id)?.name || `Vehicle #${id}`
}

async function loadBookings() {
  loading.value = true
  try {
    const { data } = await apiClient.get('/bookings/')
    bookings.value = data.results ?? data
  } catch (err) {
    error.value = 'Could not load your bookings.'
  } finally {
    loading.value = false
  }
}

async function cancelBooking(booking) {
  cancellingId.value = booking.id
  error.value = ''
  try {
    const { data } = await apiClient.post(`/bookings/${booking.id}/cancel/`)
    const index = bookings.value.findIndex((b) => b.id === booking.id)
    bookings.value[index] = data
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not cancel this booking.'
  } finally {
    cancellingId.value = null
  }
}

const canCancel = (booking) => !['cancelled', 'completed'].includes(booking.status)

onMounted(() => {
  catalog.fetchVehicles()
  loadBookings()
})
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-16 sm:px-6">
    <h1 class="text-center font-[Georgia] text-3xl font-bold text-white">My Bookings</h1>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-10 text-center text-red-400">{{ error }}</p>
    <p v-else-if="!bookings.length" class="mt-10 text-center text-slate-400">
      You haven't made any bookings yet.
      <RouterLink to="/fleet" class="font-semibold text-gold-400 hover:text-gold-300">Browse the fleet</RouterLink>
    </p>

    <div v-else class="mt-10 space-y-4">
      <div
        v-for="booking in bookings"
        :key="booking.id"
        class="rounded-xl border border-navy-800 bg-navy-900 p-5"
      >
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 class="font-[Georgia] text-lg font-bold text-white">{{ vehicleName(booking.vehicle) }}</h3>
            <p class="text-sm text-slate-400">{{ booking.start_date }} to {{ booking.end_date }}</p>
            <p class="text-sm text-slate-400">{{ booking.pickup_location }}</p>
          </div>
          <span class="text-sm font-semibold uppercase" :class="statusStyles[booking.status]">
            {{ booking.status }}
          </span>
        </div>

        <div class="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-navy-800 pt-3">
          <p class="text-sm text-slate-300">
            Total KES {{ Number(booking.total_amount).toLocaleString() }} - Paid KES
            {{ Number(booking.amount_paid).toLocaleString() }} - Balance KES
            {{ Number(booking.balance_due).toLocaleString() }}
          </p>
          <button
            v-if="canCancel(booking)"
            :disabled="cancellingId === booking.id"
            class="rounded-md border border-red-400 px-3 py-1.5 text-sm font-semibold text-red-400 transition hover:bg-red-400 hover:text-navy-950 disabled:opacity-60"
            @click="cancelBooking(booking)"
          >
            {{ cancellingId === booking.id ? 'Cancelling...' : 'Cancel Booking' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
