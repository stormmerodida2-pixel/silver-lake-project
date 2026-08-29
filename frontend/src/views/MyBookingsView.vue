<script setup>
import { defineAsyncComponent, onMounted, reactive, ref } from 'vue'

import apiClient from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useCatalogStore } from '../stores/catalog'
import { ordinal } from '../utils/format'

// Async, not a static import - Leaflet (~150KB) is only actually needed once someone clicks
// "Track" on an active booking, which most visits to this page never do. A static import would
// pull that whole chunk into every page load here regardless.
const TrackVehicleMap = defineAsyncComponent(() => import('../components/TrackVehicleMap.vue'))
const ConditionReportViewer = defineAsyncComponent(() => import('../components/ConditionReportViewer.vue'))

const auth = useAuthStore()
const catalog = useCatalogStore()
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

// Rebooking the same vehicle already rebooks the same driver (Booking._apply_default_driver
// copies vehicle.driver whenever a booking's own driver isn't set) - this just tells the
// customer that's what will happen, gated on the driver still being around to honor it. Presence
// in catalog.drivers alone confirms is_active (the /drivers/ list already excludes inactive
// ones); is_away is the one status that list wouldn't otherwise surface.
function isDriverStillAvailable(driverId) {
  const driver = catalog.drivers.find((d) => d.id === driverId)
  return Boolean(driver && !driver.is_away)
}

// ── Track vehicle ────────────────────────────────────────────────────────
const trackingId = ref(null)
const canTrack = (booking) => ['confirmed', 'ongoing'].includes(booking.status)
function toggleTracking(booking) {
  trackingId.value = trackingId.value === booking.id ? null : booking.id
}

// ── Vehicle condition report ─────────────────────────────────────────────────
// Surfaces the same pickup/return condition reports drivers already log for damage-dispute
// evidence - only relevant once a trip has actually started (they're logged at Start/End Trip).
const conditionReportId = ref(null)
const canViewConditionReport = (booking) => ['ongoing', 'completed'].includes(booking.status)
function toggleConditionReport(booking) {
  conditionReportId.value = conditionReportId.value === booking.id ? null : booking.id
}

// ── Leave a review ───────────────────────────────────────────────────────────
const reviewingId = ref(null)
const reviewSaving = ref(false)
const reviewError = ref('')
const reviewForm = reactive({ rating: 5, comment: '' })
const reviewPhoto = ref(null)
const reviewPhotoPreviewUrl = ref('')
// Only one review form is ever open at a time (reviewingId is a single value, not a set), so a
// single template ref for its file input is enough - no need to key one per booking.
const reviewPhotoInputEl = ref(null)

function openReviewForm(booking) {
  reviewingId.value = booking.id
  reviewError.value = ''
  Object.assign(reviewForm, { rating: 5, comment: '' })
  reviewPhoto.value = null
  reviewPhotoPreviewUrl.value = ''
}

function onReviewPhotoChange(event) {
  const file = event.target.files[0]
  if (reviewPhotoPreviewUrl.value) URL.revokeObjectURL(reviewPhotoPreviewUrl.value)
  reviewPhoto.value = file || null
  reviewPhotoPreviewUrl.value = file ? URL.createObjectURL(file) : ''
}

function clearReviewPhoto() {
  if (reviewPhotoPreviewUrl.value) URL.revokeObjectURL(reviewPhotoPreviewUrl.value)
  reviewPhoto.value = null
  reviewPhotoPreviewUrl.value = ''
  if (reviewPhotoInputEl.value) reviewPhotoInputEl.value.value = ''
}

async function submitReview(booking) {
  reviewError.value = ''
  if (!reviewForm.comment.trim()) {
    reviewError.value = 'Please share a few words about your experience.'
    return
  }
  reviewSaving.value = true
  try {
    // A plain object would work for the text fields alone, but the photo (optional) needs
    // multipart/form-data - same pattern as the license/ID uploads elsewhere in booking flows.
    const payload = new FormData()
    payload.append('rating', reviewForm.rating)
    payload.append('comment', reviewForm.comment.trim())
    if (reviewPhoto.value) payload.append('photo', reviewPhoto.value)
    const { data } = await apiClient.post(`/bookings/${booking.id}/review/`, payload)
    const index = bookings.value.findIndex((b) => b.id === booking.id)
    bookings.value[index] = data
    reviewingId.value = null
    clearReviewPhoto()
  } catch (err) {
    reviewError.value = err.response?.data?.detail || 'Could not submit your review.'
  } finally {
    reviewSaving.value = false
  }
}

const statusStyles = {
  pending: 'text-foreground-muted',
  confirmed: 'text-info',
  ongoing: 'text-info',
  completed: 'text-foreground-muted',
  cancelled: 'text-danger',
}

async function loadBookings() {
  loading.value = true
  try {
    const { data } = await apiClient.get('/bookings/')
    bookings.value = data.results ?? data
  } catch {
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

// ── Change dates ─────────────────────────────────────────────────────────────
// Adjusts a PENDING/CONFIRMED booking's dates in place - cheaper than cancel-and-rebook, which
// would trigger the cancellation refund rules and a whole new deposit even for a simple shift.
const canChangeDates = (booking) => ['pending', 'confirmed'].includes(booking.status)
const changingDatesId = ref(null)
const changeDatesSaving = ref(false)
const changeDatesError = ref('')
const changeDatesForm = reactive({ start_date: '', end_date: '' })

function openChangeDatesForm(booking) {
  changingDatesId.value = booking.id
  changeDatesError.value = ''
  Object.assign(changeDatesForm, { start_date: booking.start_date, end_date: booking.end_date })
}

async function submitChangeDates(booking) {
  changeDatesError.value = ''
  changeDatesSaving.value = true
  try {
    const { data } = await apiClient.post(`/bookings/${booking.id}/change_dates/`, {
      start_date: changeDatesForm.start_date,
      end_date: changeDatesForm.end_date,
    })
    const index = bookings.value.findIndex((b) => b.id === booking.id)
    bookings.value[index] = data
    changingDatesId.value = null
  } catch (err) {
    changeDatesError.value = err.response?.data?.detail || 'Could not change these dates.'
  } finally {
    changeDatesSaving.value = false
  }
}

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
  } catch {
    error.value = 'Could not download the receipt.'
  } finally {
    downloadingId.value = null
  }
}

onMounted(() => {
  loadBookings()
  catalog.fetchDrivers()
})
</script>

<template>
  <div class="bg-page">
    <div class="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <h1 class="text-center font-[Georgia] text-3xl font-bold text-foreground">My Bookings</h1>

      <p v-if="loading" class="mt-10 text-center text-foreground-subtle">Loading...</p>
      <p v-else-if="error" class="mt-10 text-center text-danger">{{ error }}</p>
      <p v-else-if="!bookings.length" class="mt-10 text-center text-foreground-subtle">
        You haven't made any bookings yet.
        <RouterLink to="/fleet" class="font-semibold text-accent hover:text-accent-strong"
          >Browse the fleet</RouterLink
        >
      </p>

      <div v-else class="mt-10 space-y-4">
        <div v-for="booking in bookings" :key="booking.id" class="rounded-xl border border-border-subtle bg-surface p-5">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 class="font-[Georgia] text-lg font-bold text-foreground">{{ booking.vehicle_name }}</h3>
              <p v-if="isBookedForSomeoneElse(booking)" class="text-sm font-semibold text-accent">
                Booking for {{ booking.customer_name }}
              </p>
              <p class="text-sm text-foreground-subtle">{{ booking.start_date }} to {{ booking.end_date }}</p>
              <p class="text-sm text-foreground-subtle">{{ booking.pickup_location }}</p>
            </div>
            <span class="text-sm font-semibold uppercase" :class="statusStyles[booking.status]">
              {{ booking.status }}
            </span>
          </div>

          <p
            v-if="booking.trip_milestone_number"
            class="mt-3 rounded-lg border border-accent-border-strong/40 bg-accent-bg/10 px-3 py-2 text-sm font-semibold text-accent"
          >
            This was your {{ ordinal(booking.trip_milestone_number) }} trip with SilverLake &#127881;
          </p>

          <div class="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle pt-3">
            <p class="text-sm text-foreground-muted">
              Total KES {{ Number(booking.total_amount).toLocaleString() }} - Paid KES
              {{ Number(booking.amount_paid).toLocaleString() }} - Balance KES
              {{ Number(booking.balance_due).toLocaleString() }}
            </p>
            <button
              v-if="canTrack(booking)"
              class="rounded-md border border-accent-border-strong px-3 py-1.5 text-sm font-semibold text-accent transition hover:bg-accent-bg hover:text-on-accent"
              @click="toggleTracking(booking)"
            >
              {{ trackingId === booking.id ? 'Hide Map' : 'Track Vehicle' }}
            </button>
            <button
              v-if="canViewConditionReport(booking)"
              class="rounded-md border border-accent-border-strong px-3 py-1.5 text-sm font-semibold text-accent transition hover:bg-accent-bg hover:text-on-accent"
              @click="toggleConditionReport(booking)"
            >
              {{ conditionReportId === booking.id ? 'Hide Condition Report' : 'View Vehicle Condition' }}
            </button>
            <button
              v-if="canChangeDates(booking) && changingDatesId !== booking.id"
              class="rounded-md border border-accent-border-strong px-3 py-1.5 text-sm font-semibold text-accent transition hover:bg-accent-bg hover:text-on-accent"
              @click="openChangeDatesForm(booking)"
            >
              Change Dates
            </button>
            <button
              v-if="canCancel(booking)"
              :disabled="cancellingId === booking.id"
              class="rounded-md border border-danger-border px-3 py-1.5 text-sm font-semibold text-danger transition hover:bg-red-500 hover:text-foreground disabled:opacity-60"
              @click="cancelBooking(booking)"
            >
              {{ cancellingId === booking.id ? 'Cancelling...' : 'Cancel Booking' }}
            </button>
            <button
              v-if="booking.status === 'completed' && !booking.review && reviewingId !== booking.id"
              class="rounded-md bg-accent-bg px-3 py-1.5 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover"
              @click="openReviewForm(booking)"
            >
              Leave a Review
            </button>
            <RouterLink
              v-if="booking.status === 'completed'"
              :to="bookAgainLink(booking)"
              class="rounded-md border border-accent-border-strong px-3 py-1.5 text-sm font-semibold text-accent transition hover:bg-accent-bg hover:text-on-accent"
            >
              {{
                booking.service_type === 'with_driver' && booking.driver && isDriverStillAvailable(booking.driver)
                  ? `Book Again with ${booking.driver_name}`
                  : 'Book Again'
              }}
            </RouterLink>
            <button
              v-if="Number(booking.amount_paid) > 0"
              :disabled="downloadingId === booking.id"
              class="rounded-md border border-border px-3 py-1.5 text-sm font-semibold text-foreground transition hover:bg-surface-2 disabled:opacity-60"
              @click="downloadReceipt(booking)"
            >
              {{ downloadingId === booking.id ? 'Downloading...' : 'Download Receipt' }}
            </button>
            <RouterLink
              :to="{ path: '/account/support', query: { booking: booking.id } }"
              class="rounded-md border border-border px-3 py-1.5 text-sm font-semibold text-foreground transition hover:bg-surface-2"
            >
              Report an Issue
            </RouterLink>
          </div>

          <TrackVehicleMap v-if="trackingId === booking.id" :booking-id="booking.id" class="mt-3" />
          <ConditionReportViewer v-if="conditionReportId === booking.id" :booking-id="booking.id" class="mt-3" />

          <!-- Change dates form -->
          <div
            v-if="changingDatesId === booking.id"
            class="mt-3 space-y-3 rounded-lg border border-border-subtle bg-surface-2 p-4"
          >
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm text-foreground-muted">New start date</label>
                <input
                  v-model="changeDatesForm.start_date"
                  type="date"
                  class="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground [color-scheme:dark] focus:border-accent-border focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm text-foreground-muted">New end date</label>
                <input
                  v-model="changeDatesForm.end_date"
                  type="date"
                  :min="changeDatesForm.start_date"
                  class="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground [color-scheme:dark] focus:border-accent-border focus:outline-none"
                />
              </div>
            </div>
            <p class="text-xs text-foreground-subtle">
              The trip total is recalculated for the new dates - if it's now lower than what you've already paid, we'll
              refund the difference.
            </p>
            <p v-if="changeDatesError" class="text-sm text-danger">{{ changeDatesError }}</p>
            <div class="flex gap-3">
              <button
                type="button"
                class="rounded-md border border-border px-3 py-1.5 text-sm font-semibold text-foreground hover:bg-surface-2"
                @click="changingDatesId = null"
              >
                Cancel
              </button>
              <button
                :disabled="changeDatesSaving"
                class="rounded-md bg-accent-bg px-3 py-1.5 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
                @click="submitChangeDates(booking)"
              >
                {{ changeDatesSaving ? 'Saving...' : 'Save New Dates' }}
              </button>
            </div>
          </div>

          <!-- Submitted review -->
          <div v-if="booking.review" class="mt-3 rounded-lg border border-border-subtle bg-surface-2 p-4">
            <p class="text-accent-strong">
              <span v-for="n in 5" :key="n">{{ n <= booking.review.rating ? '★' : '☆' }}</span>
            </p>
            <p class="mt-1 text-sm text-foreground-muted">&ldquo;{{ booking.review.comment }}&rdquo;</p>
            <img
              v-if="booking.review.photo"
              :src="booking.review.photo"
              alt="Your trip photo"
              class="mt-2 h-24 w-24 rounded-md border border-border-subtle object-cover"
            />
            <p class="mt-1 text-xs text-foreground-muted">Awaiting approval before it shows publicly.</p>
          </div>

          <!-- Review form -->
          <div
            v-else-if="reviewingId === booking.id"
            class="mt-3 space-y-3 rounded-lg border border-border-subtle bg-surface-2 p-4"
          >
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">
                Rating{{ booking.driver_name ? ` for ${booking.driver_name}` : '' }}
              </label>
              <div class="flex gap-1 text-2xl text-accent-strong">
                <button v-for="n in 5" :key="n" type="button" class="leading-none" @click="reviewForm.rating = n">
                  {{ n <= reviewForm.rating ? '★' : '☆' }}
                </button>
              </div>
            </div>
            <textarea
              v-model="reviewForm.comment"
              rows="3"
              placeholder="How was your trip?"
              class="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-accent-border focus:outline-none"
            ></textarea>

            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Add a photo (optional)</label>
              <div v-if="reviewPhotoPreviewUrl" class="flex items-center gap-3">
                <img
                  :src="reviewPhotoPreviewUrl"
                  alt="Selected photo preview"
                  class="h-16 w-16 rounded-md border border-border object-cover"
                />
                <button
                  type="button"
                  class="text-sm font-semibold text-foreground-muted hover:text-danger"
                  @click="clearReviewPhoto"
                >
                  Remove
                </button>
              </div>
              <input
                v-else
                ref="reviewPhotoInputEl"
                type="file"
                accept="image/*"
                class="w-full text-sm text-foreground-muted file:mr-3 file:rounded-md file:border-0 file:bg-accent-bg file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-on-accent"
                @change="onReviewPhotoChange"
              />
            </div>

            <p v-if="reviewError" class="text-sm text-danger">{{ reviewError }}</p>
            <div class="flex gap-3">
              <button
                type="button"
                class="rounded-md border border-border px-3 py-1.5 text-sm font-semibold text-foreground hover:bg-surface-2"
                @click="reviewingId = null"
              >
                Cancel
              </button>
              <button
                :disabled="reviewSaving"
                class="rounded-md bg-accent-bg px-3 py-1.5 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
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
