<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import apiClient from '../api/client'

const route = useRoute()
const booking = ref(null)
const loading = ref(true)
const completing = ref(false)
const error = ref('')
const success = ref(false)

async function fetchBooking() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await apiClient.get(`/driver/bookings/${route.params.token}/`)
    booking.value = data
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not load trip details. The link may have expired.'
  } finally {
    loading.value = false
  }
}

async function markCompleted() {
  if (!confirm('Are you sure you want to mark this trip as completed? This will finalize your payout.')) return
  completing.value = true
  error.value = ''
  try {
    const { data } = await apiClient.post(`/driver/bookings/${route.params.token}/complete/`, { action: 'complete' })
    booking.value = data
    success.value = true
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not complete the trip. Please check if there is an outstanding balance.'
  } finally {
    completing.value = false
  }
}

const isOngoingOrConfirmed = computed(() => ['confirmed', 'ongoing'].includes(booking.value?.status))

// Silverlake platform fee is 15% for drivers
const driverPayoutAmount = computed(() => {
  if (!booking.value) return 0
  const total = Number(booking.value.total_amount)
  return total * 0.85
})

const platformFeeAmount = computed(() => {
  if (!booking.value) return 0
  const total = Number(booking.value.total_amount)
  return total * 0.15
})

onMounted(fetchBooking)
</script>

<template>
  <div class="min-h-screen bg-navy-950 text-white">
    <div class="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      
      <!-- Header / Logo -->
      <div class="mb-8 text-center">
        <div class="font-[Georgia] text-2xl font-bold tracking-wide text-white">SILVERLAKE</div>
        <div class="text-xs tracking-widest text-gold-400">CAR RENTALS · DRIVER PORTAL</div>
      </div>

      <div v-if="loading" class="py-16 text-center text-slate-400">
        <p class="text-lg">Loading trip details...</p>
      </div>

      <div v-else-if="error && !booking" class="rounded-2xl border border-red-500/20 bg-red-500/10 p-6 text-center">
        <p class="text-red-400 font-semibold">{{ error }}</p>
        <RouterLink to="/" class="mt-4 inline-block text-sm text-gold-400 hover:underline">&larr; Back to Home</RouterLink>
      </div>

      <div v-else-if="booking" class="space-y-6">
        
        <!-- Status Bar -->
        <div class="flex items-center justify-between rounded-xl border border-navy-800 bg-navy-900/60 p-5 backdrop-blur-sm">
          <div>
            <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Booking Status</p>
            <p class="mt-1 text-lg font-bold capitalize" :class="booking.status === 'completed' ? 'text-green-400' : (booking.status === 'cancelled' ? 'text-red-400' : 'text-gold-400')">
              {{ booking.status }}
            </p>
          </div>
          <div class="text-right">
            <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Booking ID</p>
            <p class="mt-1 text-sm font-semibold">#{{ booking.id }}</p>
          </div>
        </div>

        <div v-if="success" class="rounded-xl border border-green-500/20 bg-green-500/10 p-5 text-center text-green-400">
          <p class="font-bold text-lg">Trip marked as Completed! 🎉</p>
          <p class="mt-1 text-sm text-slate-300">Your payout request has been queued in the system ledger for admin review.</p>
        </div>

        <!-- Error notification -->
        <div v-if="error" class="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-center text-red-400">
          <p class="text-sm font-medium">{{ error }}</p>
        </div>

        <!-- Main details card -->
        <div class="overflow-hidden rounded-2xl border border-navy-800 bg-navy-900/40 shadow-2xl backdrop-blur-md">
          
          <div class="border-b border-navy-800 p-6">
            <h2 class="font-[Georgia] text-xl font-bold">Trip Details</h2>
            <p class="mt-1 text-sm text-slate-400">Assigned Driver: {{ booking.driver_name }}</p>
          </div>

          <div class="p-6 space-y-6">
            <!-- Row 1: Vehicle & Customer -->
            <div class="grid gap-6 sm:grid-cols-2">
              <div>
                <p class="text-xs font-semibold uppercase tracking-wider text-slate-500">Vehicle</p>
                <p class="mt-1 text-base font-bold text-slate-200">{{ booking.vehicle_name }}</p>
              </div>
              <div>
                <p class="text-xs font-semibold uppercase tracking-wider text-slate-500">Customer</p>
                <p class="mt-1 text-base font-bold text-slate-200">{{ booking.customer_name }}</p>
                <a :href="`tel:${booking.customer_phone}`" class="mt-1 inline-flex items-center gap-1 text-sm font-semibold text-gold-400 hover:underline">
                  📞 Call Client: {{ booking.customer_phone }}
                </a>
              </div>
            </div>

            <!-- Row 2: Location & Dates -->
            <div class="grid gap-6 sm:grid-cols-2">
              <div>
                <p class="text-xs font-semibold uppercase tracking-wider text-slate-500">Dates</p>
                <p class="mt-1 text-sm text-slate-200">{{ booking.start_date }} to {{ booking.end_date }}</p>
              </div>
              <div>
                <p class="text-xs font-semibold uppercase tracking-wider text-slate-500">Pickup Location</p>
                <p class="mt-1 text-sm text-slate-200">{{ booking.pickup_location }}</p>
                <p v-if="booking.dropoff_location" class="mt-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Dropoff Location</p>
                <p v-if="booking.dropoff_location" class="mt-1 text-sm text-slate-200">{{ booking.dropoff_location }}</p>
              </div>
            </div>

            <!-- Row 3: Notes -->
            <div v-if="booking.notes">
              <p class="text-xs font-semibold uppercase tracking-wider text-slate-500">Special Notes</p>
              <p class="mt-1 text-sm text-slate-300 italic">"{{ booking.notes }}"</p>
            </div>

          </div>

          <!-- Payout detail block -->
          <div class="border-t border-navy-800 bg-navy-950/40 p-6">
            <h3 class="font-[Georgia] text-lg font-bold text-slate-300">Earnings Summary</h3>
            
            <div class="mt-4 space-y-2">
              <div class="flex justify-between text-sm text-slate-400">
                <span>Trip Subtotal</span>
                <span>KES {{ Number(booking.total_amount).toLocaleString() }}</span>
              </div>
              <div class="flex justify-between text-sm text-red-400/80">
                <span>Platform Fee (15%)</span>
                <span>- KES {{ platformFeeAmount.toLocaleString() }}</span>
              </div>
              <div class="flex justify-between border-t border-navy-800 pt-3 text-base font-bold text-white">
                <span>Your Payout</span>
                <span class="text-gold-400">KES {{ driverPayoutAmount.toLocaleString() }}</span>
              </div>
            </div>

            <div class="mt-4 rounded-lg bg-navy-900/80 p-3 text-xs text-slate-400 flex items-start gap-2">
              <span class="text-gold-400 text-sm">ℹ</span>
              <p>Wired earnings are automatically added to your pay balance ledger once complete. SilverLake processes disbursements within 24 hours.</p>
            </div>
          </div>

        </div>

        <!-- Action Button -->
        <div v-if="isOngoingOrConfirmed" class="text-center pt-4">
          <button
            :disabled="completing"
            class="w-full rounded-xl bg-gold-500 py-4 text-base font-bold text-navy-950 shadow-xl transition-all hover:bg-gold-400 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50"
            @click="markCompleted"
          >
            {{ completing ? 'Processing Completed Status...' : 'Mark Trip as Completed' }}
          </button>
        </div>

        <div v-else class="text-center text-sm text-slate-500">
          This trip is not eligible for completion updates (currently {{ booking.status }}).
        </div>

      </div>
    </div>
  </div>
</template>
