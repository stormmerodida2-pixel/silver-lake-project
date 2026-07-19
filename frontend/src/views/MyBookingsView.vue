<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../api/client'
import TrackVehicleMap from '../components/TrackVehicleMap.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const bookings = ref([])
const loading = ref(true)
const cancellingId = ref(null)
const error = ref('')

// A booking made for someone else has a customer_name that doesn't match your own account -
// worth calling out so a list of several bookings doesn't read as if they're all your own trips.
const ownName = () => `${auth.user?.first_name || ''} ${auth.user?.last_name || ''}`.trim()
const isBookedForSomeoneElse = (booking) => booking.customer_name && booking.customer_name !== ownName()

// ── Book again ────────────────────────────────────────────────────────────────
// Pre-fills the same vehicle/pickup/dropoff on a fresh booking form - only the dates (and
// payment) still need picking, since a completed trip's own dates are obviously in the past.
function bookAgainLink(booking) {
  return {
    path: '/book',
    query: {
      vehicle: booking.vehicle,
      service: booking.service_type,
      pickup: booking.pickup_location || undefined,
      dropoff: booking.dropoff_location || undefined,
    },
  }
}

// ── Track vehicle ────────────────────────────────────────────────────────
const trackingId = ref(null)
const canTrack = (booking) => ['confirmed', 'ongoing'].includes(booking.status)
function toggleTracking(booking) {
  trackingId.value = trackingId.value === booking.id ? null : booking.id
}

// ── Leave a review ───────────────────────────────────────────────────────────
const reviewingId = ref(null)
const reviewSaving = ref(false)
const reviewError = ref('')
const reviewForm = reactive({ rating: 5, comment: '' })

function openReviewForm(booking) {
  reviewingId.value = booking.id
  reviewError.value = ''
  Object.assign(reviewForm, { rating: 5, comment: '' })
}

async function submitReview(booking) {
  reviewError.value = ''
  if (!reviewForm.comment.trim()) {
    reviewError.value = 'Please share a few words about your experience.'
    return
  }
  reviewSaving.value = true
  try {
    const { data } = await apiClient.post(`/bookings/${booking.id}/review/`, {
      rating: reviewForm.rating,
      comment: reviewForm.comment.trim(),
    })
    const index = bookings.value.findIndex((b) => b.id === booking.id)
    bookings.value[index] = data
    reviewingId.value = null
  } catch (err) {
    reviewError.value = err.response?.data?.detail || 'Could not submit your review.'
  } finally {
    reviewSaving.value = false
  }
}

const statusStyles = {
  pending: 'text-slate-500',
  confirmed: 'text-brand-blue-600',
  ongoing: 'text-brand-blue-600',
  completed: 'text-slate-500',
  cancelled: 'text-red-600',
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

// ── Download receipt ─────────────────────────────────────────────────────────
const downloadingId = ref(null)
async function downloadReceipt(booking) {
  downloadingId.value = booking.id
  error.value = ''
  try {
    const response = await apiClient.get(`/bookings/${booking.id}/receipt/`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `SilverLake-Receipt-${booking.id}.pdf`
    link.click()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    error.value = 'Could not download the receipt.'
  } finally {
    downloadingId.value = null
  }
}

onMounted(() => {
  loadBookings()
})
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <h1 class="text-center font-[Georgia] text-3xl font-bold text-navy-900">My Bookings</h1>

      <p v-if="loading" class="mt-10 text-center text-slate-500">Loading...</p>
      <p v-else-if="error" class="mt-10 text-center text-red-600">{{ error }}</p>
      <p v-else-if="!bookings.length" class="mt-10 text-center text-slate-500">
        You haven't made any bookings yet.
        <RouterLink to="/fleet" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500">Browse the fleet</RouterLink>
      </p>

      <div v-else class="mt-10 space-y-4">
        <div
          v-for="booking in bookings"
          :key="booking.id"
          class="rounded-xl border border-slate-200 bg-slate-50 p-5"
        >
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 class="font-[Georgia] text-lg font-bold text-navy-900">{{ booking.vehicle_name }}</h3>
              <p v-if="isBookedForSomeoneElse(booking)" class="text-sm font-semibold text-brand-blue-600">
                Booking for {{ booking.customer_name }}
              </p>
              <p class="text-sm text-slate-500">{{ booking.start_date }} to {{ booking.end_date }}</p>
              <p class="text-sm text-slate-500">{{ booking.pickup_location }}</p>
            </div>
            <span class="text-sm font-semibold uppercase" :class="statusStyles[booking.status]">
              {{ booking.status }}
            </span>
          </div>

          <div class="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-3">
            <p class="text-sm text-slate-600">
              Total KES {{ Number(booking.total_amount).toLocaleString() }} - Paid KES
              {{ Number(booking.amount_paid).toLocaleString() }} - Balance KES
              {{ Number(booking.balance_due).toLocaleString() }}
            </p>
            <button
              v-if="canTrack(booking)"
              class="rounded-md border border-brand-blue-600 px-3 py-1.5 text-sm font-semibold text-brand-blue-600 transition hover:bg-brand-blue-600 hover:text-white"
              @click="toggleTracking(booking)"
            >
              {{ trackingId === booking.id ? 'Hide Map' : 'Track Vehicle' }}
            </button>
            <button
              v-if="canCancel(booking)"
              :disabled="cancellingId === booking.id"
              class="rounded-md border border-red-400 px-3 py-1.5 text-sm font-semibold text-red-600 transition hover:bg-red-500 hover:text-white disabled:opacity-60"
              @click="cancelBooking(booking)"
            >
              {{ cancellingId === booking.id ? 'Cancelling...' : 'Cancel Booking' }}
            </button>
            <button
              v-if="booking.status === 'completed' && !booking.review && reviewingId !== booking.id"
              class="rounded-md bg-gold-500 px-3 py-1.5 text-sm font-semibold text-navy-950 transition hover:bg-gold-400"
              @click="openReviewForm(booking)"
            >
              Leave a Review
            </button>
            <RouterLink
              v-if="booking.status === 'completed'"
              :to="bookAgainLink(booking)"
              class="rounded-md border border-brand-blue-600 px-3 py-1.5 text-sm font-semibold text-brand-blue-600 transition hover:bg-brand-blue-600 hover:text-white"
            >
              Book Again
            </RouterLink>
            <button
              v-if="Number(booking.amount_paid) > 0"
              :disabled="downloadingId === booking.id"
              class="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-600 transition hover:border-slate-400 disabled:opacity-60"
              @click="downloadReceipt(booking)"
            >
              {{ downloadingId === booking.id ? 'Downloading...' : 'Download Receipt' }}
            </button>
          </div>

          <TrackVehicleMap v-if="trackingId === booking.id" :booking-id="booking.id" class="mt-3" />

          <!-- Submitted review -->
          <div v-if="booking.review" class="mt-3 rounded-lg border border-slate-200 bg-white p-4">
            <p class="text-gold-500">
              <span v-for="n in 5" :key="n">{{ n <= booking.review.rating ? '★' : '☆' }}</span>
            </p>
            <p class="mt-1 text-sm text-slate-600">&ldquo;{{ booking.review.comment }}&rdquo;</p>
            <p class="mt-1 text-xs text-slate-400">Awaiting approval before it shows publicly.</p>
          </div>

          <!-- Review form -->
          <div v-else-if="reviewingId === booking.id" class="mt-3 space-y-3 rounded-lg border border-slate-200 bg-white p-4">
            <div>
              <label class="mb-1 block text-sm text-slate-600">
                Rating{{ booking.driver_name ? ` for ${booking.driver_name}` : '' }}
              </label>
              <div class="flex gap-1 text-2xl text-gold-500">
                <button
                  v-for="n in 5" :key="n" type="button"
                  class="leading-none"
                  @click="reviewForm.rating = n"
                >
                  {{ n <= reviewForm.rating ? '★' : '☆' }}
                </button>
              </div>
            </div>
            <textarea
              v-model="reviewForm.comment"
              rows="3"
              placeholder="How was your trip?"
              class="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-navy-900 focus:border-brand-blue-500 focus:outline-none"
            ></textarea>
            <p v-if="reviewError" class="text-sm text-red-600">{{ reviewError }}</p>
            <div class="flex gap-3">
              <button
                type="button"
                class="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-600 hover:border-slate-400"
                @click="reviewingId = null"
              >
                Cancel
              </button>
              <button
                :disabled="reviewSaving"
                class="rounded-md bg-gold-500 px-3 py-1.5 text-sm font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
                @click="submitReview(booking)"
              >
                {{ reviewSaving ? 'Submitting...' : 'Submit Review' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
