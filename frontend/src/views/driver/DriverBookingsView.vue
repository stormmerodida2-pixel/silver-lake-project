<script setup>
import { onMounted, onUnmounted, ref } from 'vue'

import apiClient from '../../api/client'
import BookingPaymentCollector from '../../components/driver/BookingPaymentCollector.vue'
import WalkUpBookingModal from '../../components/driver/WalkUpBookingModal.vue'
import { useDriverPortalStore } from '../../stores/driverPortal'
import { confirmDialog } from '../../utils/dialogs'

const driverPortal = useDriverPortalStore()

const statusLabels = {
  pending: 'Pending',
  confirmed: 'Confirmed',
  ongoing: 'Ongoing',
  completed: 'Completed',
  cancelled: 'Cancelled',
}
const statusClasses = {
  pending: 'bg-gold-500/10 text-gold-400',
  confirmed: 'bg-brand-blue-500/10 text-brand-blue-400',
  ongoing: 'bg-brand-blue-500/10 text-brand-blue-400',
  completed: 'bg-emerald-500/10 text-emerald-400',
  cancelled: 'bg-red-500/10 text-red-400',
}

const acknowledgingId = ref(null)

async function acknowledgeBooking(booking) {
  acknowledgingId.value = booking.id
  try {
    const { data } = await apiClient.post(`/driver/bookings/${booking.id}/acknowledge/`)
    Object.assign(booking, data)
  } catch (err) {
    driverPortal.bookingsError = 'Could not acknowledge this booking.'
  } finally {
    acknowledgingId.value = null
  }
}

// ── Acknowledgment deadline countdown ────────────────────────────────────────
// Ticks every minute purely to keep the countdown text fresh - the list itself only reloads
// on an explicit action, and per-second precision isn't needed for a multi-hour deadline.
const now = ref(Date.now())
let ackClockIntervalId = null

function ackDeadlineInfo(booking) {
  if (booking.driver_acknowledged_at || !booking.acknowledgment_deadline) return null
  const diffMs = new Date(booking.acknowledgment_deadline).getTime() - now.value
  const overdue = diffMs < 0
  const totalMinutes = Math.round(Math.abs(diffMs) / 60000)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  const timeStr = hours ? `${hours}h ${minutes}m` : `${minutes}m`
  return {
    label: overdue ? `Overdue by ${timeStr}` : `Acknowledge within ${timeStr}`,
    urgent: overdue || diffMs < 15 * 60000,
  }
}

const completingId = ref(null)

async function completeBooking(booking) {
  if (!(await confirmDialog(`Mark the trip for ${booking.customer_name} as completed?`))) return
  completingId.value = booking.id
  try {
    const { data } = await apiClient.post(`/driver/bookings/${booking.id}/complete/`)
    Object.assign(booking, data)
  } catch (err) {
    driverPortal.bookingsError = err.response?.data?.detail || 'Could not complete this trip.'
  } finally {
    completingId.value = null
  }
}

// ── Start / End trip (separate from payment - confirms what actually happened) ──────────────
const startingId = ref(null)
const endingId = ref(null)

async function startTrip(booking) {
  startingId.value = booking.id
  try {
    const { data } = await apiClient.post(`/driver/bookings/${booking.id}/start-trip/`)
    Object.assign(booking, data)
  } catch (err) {
    driverPortal.bookingsError = err.response?.data?.detail || 'Could not start this trip.'
  } finally {
    startingId.value = null
  }
}

async function endTrip(booking) {
  if (!(await confirmDialog(`Confirm the vehicle has been returned for ${booking.customer_name}'s trip?`))) return
  endingId.value = booking.id
  try {
    const { data } = await apiClient.post(`/driver/bookings/${booking.id}/end-trip/`)
    Object.assign(booking, data)
  } catch (err) {
    driverPortal.bookingsError = err.response?.data?.detail || 'Could not end this trip.'
  } finally {
    endingId.value = null
  }
}

// ── Live location sharing ────────────────────────────────────────────────────
// Reported from the driver's own browser via the Geolocation API - only works while this tab
// stays open, there's no background/native tracking. Only one trip can share at a time.
const LOCATION_INTERVAL_MS = 30000
const sharingBookingId = ref(null)
let locationIntervalId = null

function isTripCurrentlyActive(booking) {
  if (!['confirmed', 'ongoing'].includes(booking.status)) return false
  const today = new Date().toISOString().slice(0, 10)
  return booking.start_date <= today && today <= booking.end_date
}

function reportPosition(bookingId) {
  if (!navigator.geolocation) return
  navigator.geolocation.getCurrentPosition(
    (position) => {
      apiClient.post(`/driver/bookings/${bookingId}/location/`, {
        lat: position.coords.latitude,
        lng: position.coords.longitude,
      }).catch(() => {
        // Silently retry on the next interval tick - a single dropped update isn't worth
        // interrupting the driver over.
      })
    },
    () => {
      driverPortal.bookingsError = 'Could not read your location. Check your browser location permission.'
      stopSharingLocation()
    },
  )
}

function startSharingLocation(booking) {
  if (!navigator.geolocation) {
    driverPortal.bookingsError = 'Location sharing is not supported in this browser.'
    return
  }
  stopSharingLocation()
  sharingBookingId.value = booking.id
  reportPosition(booking.id)
  locationIntervalId = setInterval(() => reportPosition(booking.id), LOCATION_INTERVAL_MS)
}

function stopSharingLocation() {
  if (locationIntervalId) {
    clearInterval(locationIntervalId)
    locationIntervalId = null
  }
  sharingBookingId.value = null
}

function toggleSharingLocation(booking) {
  if (sharingBookingId.value === booking.id) {
    stopSharingLocation()
  } else {
    startSharingLocation(booking)
  }
}

onUnmounted(() => {
  stopSharingLocation()
  clearInterval(ackClockIntervalId)
})

onMounted(() => {
  ackClockIntervalId = setInterval(() => { now.value = Date.now() }, 60000)
})

// ── Walk-up client booking ───────────────────────────────────────────────────
const showOnsiteModal = ref(false)
const onsiteModal = ref(null)

function openOnsiteModal() {
  onsiteModal.value.open()
  showOnsiteModal.value = true
}
</script>

<template>
  <div>
    <section>
      <h2 class="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gold-400">
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M8 3v4M16 3v4M4 9h16M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z" />
        </svg>
        My Bookings
      </h2>
      <p class="mt-1 text-xs text-slate-500">
        Trips customers have booked with you online - approve a new one to let us know you've seen it.
      </p>

      <p v-if="driverPortal.bookingsError" class="mt-3 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">
        {{ driverPortal.bookingsError }}
      </p>

      <div class="mt-3 space-y-3">
        <div
          v-for="booking in driverPortal.bookings"
          :key="booking.id"
          class="rounded-xl border p-4 transition"
          :class="!booking.driver_acknowledged_at ? 'border-gold-500 bg-navy-900' : 'border-navy-800 bg-navy-900 hover:border-navy-700'"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="font-semibold text-white">{{ booking.customer_name }}</p>
              <p class="text-xs text-slate-400">
                {{ booking.vehicle_name }} &middot; {{ booking.start_date }} to {{ booking.end_date }}
              </p>
              <p class="text-xs text-slate-500">{{ booking.pickup_location }}</p>
              <div v-if="booking.status === 'completed' && booking.review" class="mt-1.5 flex items-center gap-1">
                <span class="text-sm leading-none text-gold-400">
                  <span v-for="n in 5" :key="n">{{ n <= booking.review.rating ? '★' : '☆' }}</span>
                </span>
                <span class="text-xs text-slate-500">customer rating</span>
              </div>
              <p v-if="booking.status === 'completed' && booking.review?.comment" class="mt-1 max-w-sm text-xs italic text-slate-400">
                “{{ booking.review.comment }}”
              </p>
            </div>
            <span
              class="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold"
              :class="statusClasses[booking.status]"
            >
              {{ statusLabels[booking.status] || booking.status }}
            </span>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <span v-if="booking.driver_acknowledged_at" class="mr-auto text-xs font-semibold text-emerald-400">
              Acknowledged
            </span>
            <template v-else>
              <div class="mr-auto flex flex-col items-start gap-1">
                <button
                  :disabled="acknowledgingId === booking.id"
                  class="rounded-md bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                  @click="acknowledgeBooking(booking)"
                >
                  {{ acknowledgingId === booking.id ? 'Approving...' : 'Approve' }}
                </button>
                <span
                  v-if="ackDeadlineInfo(booking)"
                  class="text-xs font-semibold"
                  :class="ackDeadlineInfo(booking).urgent ? 'text-red-400' : 'text-slate-400'"
                >
                  {{ ackDeadlineInfo(booking).label }}
                </span>
              </div>
            </template>

            <button
              v-if="booking.status === 'confirmed'"
              :disabled="startingId === booking.id"
              class="rounded-md border border-navy-700 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
              @click="startTrip(booking)"
            >
              {{ startingId === booking.id ? 'Starting...' : 'Start Trip' }}
            </button>

            <button
              v-if="['confirmed', 'ongoing'].includes(booking.status) && !booking.trip_ended_at"
              :disabled="endingId === booking.id"
              class="rounded-md border border-navy-700 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
              @click="endTrip(booking)"
            >
              {{ endingId === booking.id ? 'Ending...' : 'End Trip' }}
            </button>

            <button
              v-if="['confirmed', 'ongoing'].includes(booking.status)"
              :disabled="completingId === booking.id"
              class="rounded-md border border-navy-700 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
              @click="completeBooking(booking)"
            >
              {{ completingId === booking.id ? 'Completing...' : 'Complete Trip' }}
            </button>

            <button
              v-if="isTripCurrentlyActive(booking)"
              class="rounded-md px-3 py-1.5 text-xs font-semibold"
              :class="sharingBookingId === booking.id
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/40'
                : 'border border-navy-700 text-slate-300 hover:border-gold-400 hover:text-gold-400'"
              @click="toggleSharingLocation(booking)"
            >
              {{ sharingBookingId === booking.id ? '● Sharing Location' : 'Share My Location' }}
            </button>
          </div>

          <BookingPaymentCollector :booking="booking" />
        </div>
        <p v-if="!driverPortal.bookingsLoading && !driverPortal.bookings.length" class="text-sm text-slate-500">No bookings yet.</p>
      </div>
    </section>

    <!-- Walk-up client booking -->
    <section class="mt-10">
      <h2 class="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gold-400">
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M17 20h5v-2a4 4 0 0 0-3-3.87M9 20H4v-2a4 4 0 0 1 3-3.87m5-2.13a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm7-4a4 4 0 0 1-3 3.87" />
        </svg>
        Walk-Up Client
      </h2>
      <div class="mt-3 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-navy-800 bg-navy-900 p-4">
        <p class="max-w-md text-xs text-slate-400">
          For a client with you right now who doesn't want to register - creates their booking,
          then lets you collect cash, card, or M-Pesa for the exact amount they tell you.
        </p>
        <button
          v-if="driverPortal.profile.vehicles.length"
          class="flex shrink-0 items-center gap-2 rounded-lg bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 transition hover:bg-gold-400"
          @click="openOnsiteModal"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Book For a Client On-Site
        </button>
      </div>
    </section>

    <WalkUpBookingModal ref="onsiteModal" v-model="showOnsiteModal" />
  </div>
</template>
