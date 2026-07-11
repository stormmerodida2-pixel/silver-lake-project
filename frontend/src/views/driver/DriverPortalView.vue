<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import apiClient from '../../api/client'
import AnnouncementBanner from '../../components/AnnouncementBanner.vue'
import NotificationBell from '../../components/NotificationBell.vue'
import SilverLakeLogo from '../../components/SilverLakeLogo.vue'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const initials = computed(() => {
  const name = profile.value?.full_name || ''
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return (parts[0]?.[0] || '') + (parts[1]?.[0] || '')
})
const pendingBookingsCount = computed(() => bookings.value.filter((b) => !b.driver_acknowledged_at).length)
const activeTripsCount = computed(() => bookings.value.filter((b) => ['confirmed', 'ongoing'].includes(b.status)).length)
const completedTripsCount = computed(() => bookings.value.filter((b) => b.status === 'completed').length)
const serviceDueCount = computed(() => (profile.value?.vehicles || []).filter((v) => v.is_service_due).length)

function scrollToSection(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const profile = ref(null)
const loading = ref(true)
const error = ref('')

const categories = ref([])
async function loadCategories() {
  const { data } = await apiClient.get('/categories/')
  categories.value = data.results ?? data
}

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

// ── My bookings (online customers booking this driver) ──────────────────────
const { items: bookings, loading: bookingsLoading, error: bookingsError, load: loadBookings } = useAdminList('/driver/bookings/mine/')
const acknowledgingId = ref(null)

async function acknowledgeBooking(booking) {
  acknowledgingId.value = booking.id
  try {
    const { data } = await apiClient.post(`/driver/bookings/${booking.id}/acknowledge/`)
    Object.assign(booking, data)
  } catch (err) {
    bookingsError.value = 'Could not acknowledge this booking.'
  } finally {
    acknowledgingId.value = null
  }
}

const completingId = ref(null)

async function completeBooking(booking) {
  if (!confirm(`Mark the trip for ${booking.customer_name} as completed?`)) return
  completingId.value = booking.id
  try {
    const { data } = await apiClient.post(`/driver/bookings/${booking.id}/complete/`)
    Object.assign(booking, data)
  } catch (err) {
    bookingsError.value = err.response?.data?.detail || 'Could not complete this trip.'
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
    bookingsError.value = err.response?.data?.detail || 'Could not start this trip.'
  } finally {
    startingId.value = null
  }
}

async function endTrip(booking) {
  if (!confirm(`Confirm the vehicle has been returned for ${booking.customer_name}'s trip?`)) return
  endingId.value = booking.id
  try {
    const { data } = await apiClient.post(`/driver/bookings/${booking.id}/end-trip/`)
    Object.assign(booking, data)
  } catch (err) {
    bookingsError.value = err.response?.data?.detail || 'Could not end this trip.'
  } finally {
    endingId.value = null
  }
}

// ── Collect payment: client picks cash/card/M-Pesa + the exact amount they're paying; cash/card
// then need the driver to separately confirm they actually received it (amount locked, not
// re-entered) - M-Pesa fires an STK Push immediately instead. Shared between "My Bookings" and
// the walk-up booking success screen, since both just need a `booking` to act on. ───────────────
const paymentFormBookingId = ref(null)
const paymentMethodDraft = ref('cash')
const paymentAmountDraft = ref('')
const declaringPaymentId = ref(null)
const declareError = ref('')
const confirmingPaymentId = ref(null)
const confirmError = ref('')

function openPaymentForm(booking) {
  paymentFormBookingId.value = booking.id
  paymentMethodDraft.value = 'cash'
  paymentAmountDraft.value = booking.balance_due
  declareError.value = ''
}

async function declarePayment(booking) {
  if (!paymentAmountDraft.value) return
  declareError.value = ''
  declaringPaymentId.value = booking.id
  try {
    const { data } = await apiClient.post(`/driver/bookings/${booking.id}/declare-payment/`, {
      method: paymentMethodDraft.value,
      amount: paymentAmountDraft.value,
    })
    Object.assign(booking, data)
    paymentFormBookingId.value = null
  } catch (err) {
    declareError.value = err.response?.data?.detail || 'Could not declare this payment.'
  } finally {
    declaringPaymentId.value = null
  }
}

async function confirmPayment(booking, payment) {
  confirmError.value = ''
  confirmingPaymentId.value = payment.id
  try {
    const { data } = await apiClient.post(`/driver/payments/${payment.id}/confirm/`)
    Object.assign(booking, data)
  } catch (err) {
    confirmError.value = err.response?.data?.detail || 'Could not confirm this payment.'
  } finally {
    confirmingPaymentId.value = null
  }
}

// ── Cash deposits (logging that collected cash was actually deposited to the Paybill) ───────
const depositFormPaymentId = ref(null)
const depositAmountDraft = ref('')
const depositReferenceDraft = ref('')
const loggingDepositId = ref(null)
const depositError = ref('')

function openDepositForm(payment) {
  depositFormPaymentId.value = payment.id
  depositAmountDraft.value = payment.amount
  depositReferenceDraft.value = ''
  depositError.value = ''
}

async function logCashDeposit(booking, payment) {
  if (!depositAmountDraft.value || !depositReferenceDraft.value.trim()) return
  depositError.value = ''
  loggingDepositId.value = payment.id
  try {
    const { data } = await apiClient.post(`/driver/payments/${payment.id}/deposit/`, {
      amount: depositAmountDraft.value,
      mpesa_reference: depositReferenceDraft.value.trim(),
    })
    Object.assign(booking, data)
    depositFormPaymentId.value = null
  } catch (err) {
    depositError.value = err.response?.data?.detail || 'Could not log this deposit.'
  } finally {
    loggingDepositId.value = null
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
      bookingsError.value = 'Could not read your location. Check your browser location permission.'
      stopSharingLocation()
    },
  )
}

function startSharingLocation(booking) {
  if (!navigator.geolocation) {
    bookingsError.value = 'Location sharing is not supported in this browser.'
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
})

async function loadProfile() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await apiClient.get('/driver/me/')
    profile.value = data
  } catch (err) {
    error.value = 'Could not load your driver profile.'
  } finally {
    loading.value = false
  }
}

// ── Service history (per vehicle) ────────────────────────────────────────────
const serviceFormVehicleId = ref(null)
const serviceDateDraft = ref('')
const serviceNotesDraft = ref('')
const loggingServiceId = ref(null)
const serviceError = ref('')

function openServiceForm(vehicleId) {
  serviceFormVehicleId.value = vehicleId
  serviceDateDraft.value = new Date().toISOString().slice(0, 10)
  serviceNotesDraft.value = ''
  serviceError.value = ''
}

async function logService(vehicle) {
  if (!serviceDateDraft.value) return
  serviceError.value = ''
  loggingServiceId.value = vehicle.id
  try {
    const { data } = await apiClient.post('/driver/service-records/', {
      vehicle: vehicle.id,
      service_date: serviceDateDraft.value,
      notes: serviceNotesDraft.value.trim(),
    })
    vehicle.service_records = [data, ...(vehicle.service_records || [])]
    serviceFormVehicleId.value = null
  } catch (err) {
    const detail = err?.response?.data
    serviceError.value = typeof detail === 'object'
      ? Object.values(detail).flat().join(' ')
      : 'Could not log this service.'
  } finally {
    loggingServiceId.value = null
  }
}

// ── Away / Available toggle ─────────────────────────────────────────────────
const awaySaving = ref(false)
const awayReasonDraft = ref('')
const showAwayForm = ref(false)

function openAwayForm() {
  awayReasonDraft.value = ''
  showAwayForm.value = true
}

async function markAway() {
  if (!awayReasonDraft.value.trim()) return
  awaySaving.value = true
  try {
    const { data } = await apiClient.patch('/driver/away/', {
      is_away: true,
      away_reason: awayReasonDraft.value.trim(),
    })
    profile.value = data
    showAwayForm.value = false
  } catch (err) {
    error.value = 'Could not update your availability.'
  } finally {
    awaySaving.value = false
  }
}

async function markAvailable() {
  awaySaving.value = true
  try {
    const { data } = await apiClient.patch('/driver/away/', { is_away: false, away_reason: '' })
    profile.value = data
  } catch (err) {
    error.value = 'Could not update your availability.'
  } finally {
    awaySaving.value = false
  }
}

// ── Walk-up client booking ───────────────────────────────────────────────────
const showOnsiteModal = ref(false)
const onsiteSaving = ref(false)
const onsiteError = ref('')
const onsiteForm = reactive({
  vehicle: '',
  customer_name: '',
  customer_phone: '',
  customer_email: '',
  pickup_location: '',
  dropoff_location: '',
  start_date: '',
  end_date: '',
  notes: '',
})
const onsiteResult = ref(null) // { booking, payment_url } after creation
const today = new Date().toISOString().split('T')[0]

function openOnsiteModal() {
  Object.assign(onsiteForm, {
    vehicle: '', customer_name: '', customer_phone: '', customer_email: '',
    pickup_location: '', dropoff_location: '', start_date: '', end_date: '', notes: '',
  })
  onsiteError.value = ''
  onsiteResult.value = null
  showOnsiteModal.value = true
}

async function submitOnsiteBooking() {
  onsiteError.value = ''
  onsiteSaving.value = true
  try {
    const { data } = await apiClient.post('/driver/bookings/create/', onsiteForm)
    onsiteResult.value = data
    openPaymentForm(onsiteResult.value.booking)
  } catch (err) {
    const detail = err?.response?.data
    onsiteError.value = typeof detail === 'object'
      ? Object.values(detail).flat().join(' ')
      : 'Could not create this booking.'
  } finally {
    onsiteSaving.value = false
  }
}

async function copyPaymentLink() {
  if (!onsiteResult.value) return
  await navigator.clipboard.writeText(onsiteResult.value.payment_url)
}

// ── Add Vehicle modal ────────────────────────────────────────────────────────
const showModal = ref(false)
const saving = ref(false)
const formError = ref('')
const form = reactive({
  name: '',
  category: '',
  tagline: '',
  description: '',
  passenger_capacity: 4,
  price_per_day: '',
})
const photoFiles = ref([])
const photoPreviewUrls = ref([])
const logbookFile = ref(null)

function openModal() {
  Object.assign(form, {
    name: '', category: categories.value[0]?.slug || '', tagline: '', description: '',
    passenger_capacity: 4, price_per_day: '',
  })
  photoFiles.value = []
  photoPreviewUrls.value = []
  logbookFile.value = null
  formError.value = ''
  showModal.value = true
}

function onPhotosSelected(event) {
  photoFiles.value = Array.from(event.target.files)
  photoPreviewUrls.value = photoFiles.value.map((file) => URL.createObjectURL(file))
}

async function submitVehicle() {
  formError.value = ''
  if (!form.name.trim() || !form.price_per_day || !logbookFile.value) {
    formError.value = 'Vehicle name, price per day, and logbook document are required.'
    return
  }
  if (photoFiles.value.length < 2) {
    formError.value = 'Please add at least 2 photos of the vehicle.'
    return
  }
  saving.value = true
  try {
    const payload = new FormData()
    Object.entries(form).forEach(([key, value]) => payload.append(key, value))
    photoFiles.value.forEach((file) => payload.append('images', file))
    payload.append('logbook_document', logbookFile.value)

    const { data } = await apiClient.post('/driver/vehicle-submissions/', payload)
    profile.value.vehicle_submissions.unshift(data)
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    formError.value = typeof detail === 'object'
      ? Object.values(detail).flat().join(' ')
      : 'Could not submit this vehicle. Please try again.'
  } finally {
    saving.value = false
  }
}

function handleLogout() {
  if (!confirm('Are you sure you want to log out?')) return
  auth.logout()
  router.push('/')
}

onMounted(() => {
  loadProfile()
  loadBookings()
  loadCategories()
})
</script>

<template>
  <div class="min-h-screen bg-navy-950">
    <header class="flex items-center justify-between border-b border-navy-800 bg-navy-950/95 px-4 py-4 backdrop-blur sm:px-8">
      <div class="flex items-center gap-2.5">
        <SilverLakeLogo :size="26" />
        <div>
          <h1 class="font-[Georgia] text-lg font-bold leading-tight text-white">Driver Portal</h1>
          <p class="text-xs text-slate-400">SilverLake Car Rentals</p>
        </div>
      </div>
      <div class="flex items-center gap-3 sm:gap-5">
        <NotificationBell base-path="/driver/notifications" />
        <RouterLink to="/" class="hidden items-center gap-1.5 text-sm font-medium text-slate-300 transition hover:text-gold-400 sm:flex">
          <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          Back to Site
        </RouterLink>
        <button class="flex items-center gap-1.5 text-sm font-medium text-slate-300 transition hover:text-gold-400" @click="handleLogout">
          <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 5v1a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3h4a3 3 0 0 1 3 3v1" />
          </svg>
          <span class="hidden sm:inline">Log Out</span>
        </button>
      </div>
    </header>

    <main class="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <AnnouncementBanner class="mb-6" />

      <p v-if="loading" class="text-center text-slate-400">Loading...</p>
      <p v-else-if="error" class="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ error }}</p>

      <template v-else-if="profile">
        <!-- Profile hero -->
        <section class="overflow-hidden rounded-2xl border border-gold-500/40 bg-gradient-to-br from-navy-900 to-navy-950 p-6 sm:p-8">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div class="flex items-center gap-4">
              <div class="flex h-16 w-16 shrink-0 items-center justify-center rounded-full border border-gold-500/40 bg-gold-500/10 font-[Georgia] text-2xl font-bold text-gold-400">
                {{ initials || '—' }}
              </div>
              <div>
                <h2 class="font-[Georgia] text-2xl font-bold text-white">{{ profile.full_name }}</h2>
                <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-400">
                  <span class="inline-flex items-center gap-1 text-gold-400">
                    <span v-for="n in 5" :key="n" class="text-sm leading-none">{{ n <= Math.round(profile.rating) ? '★' : '☆' }}</span>
                    <span class="ml-1 text-slate-300">{{ Number(profile.rating).toFixed(1) }}</span>
                  </span>
                  <span class="text-slate-600">&middot;</span>
                  <span>{{ profile.years_of_experience }} years experience</span>
                </div>
              </div>
            </div>
            <span
              class="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold"
              :class="profile.is_away ? 'bg-red-500/10 text-red-400' : 'bg-emerald-500/10 text-emerald-400'"
            >
              <span class="h-1.5 w-1.5 rounded-full" :class="profile.is_away ? 'bg-red-400' : 'bg-emerald-400'" />
              {{ profile.is_away ? 'Away' : 'Available' }}
            </span>
          </div>

          <p v-if="profile.is_away && profile.away_reason" class="mt-4 rounded-lg bg-navy-800 px-4 py-3 text-sm text-slate-300">
            <span class="font-semibold text-slate-400">Your reason: </span>{{ profile.away_reason }}
          </p>
          <p class="mt-4 text-xs text-slate-500">
            While marked away, your vehicle(s) won't show up in the public fleet for customers to book.
            Admins can still see your reason.
          </p>

          <div class="mt-4">
            <button
              v-if="!profile.is_away && !showAwayForm"
              class="rounded-md border border-red-400 px-4 py-2 text-sm font-semibold text-red-400 transition hover:bg-red-400 hover:text-navy-950"
              @click="openAwayForm"
            >
              Mark Myself Away
            </button>
            <button
              v-else-if="profile.is_away"
              :disabled="awaySaving"
              class="rounded-md bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-50"
              @click="markAvailable"
            >
              {{ awaySaving ? 'Updating...' : "I'm Available Again" }}
            </button>

            <div v-if="showAwayForm && !profile.is_away" class="mt-3 space-y-3">
              <textarea
                v-model="awayReasonDraft"
                rows="2"
                placeholder="Reason (visible to admins only) - e.g. Sick leave until Friday"
                class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
              ></textarea>
              <div class="flex gap-3">
                <button
                  class="rounded-md border border-navy-700 px-4 py-2 text-sm font-semibold text-slate-300 hover:border-slate-500"
                  @click="showAwayForm = false"
                >
                  Cancel
                </button>
                <button
                  :disabled="awaySaving || !awayReasonDraft.trim()"
                  class="rounded-md bg-red-500 px-4 py-2 text-sm font-semibold text-white hover:bg-red-400 disabled:opacity-50"
                  @click="markAway"
                >
                  {{ awaySaving ? 'Saving...' : 'Confirm Away' }}
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- Quick stats -->
        <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <button
            class="rounded-xl border border-navy-800 bg-navy-900 p-4 text-left transition hover:border-gold-400"
            @click="scrollToSection('vehicles-section')"
          >
            <p class="text-xs text-slate-400">Live Vehicles</p>
            <p class="mt-1 text-xl font-bold text-white">{{ profile.vehicles.length }}</p>
          </button>
          <button
            class="rounded-xl border p-4 text-left transition"
            :class="serviceDueCount ? 'border-gold-500 hover:border-gold-400' : 'border-navy-800 hover:border-gold-400'"
            @click="scrollToSection('vehicles-section')"
          >
            <p class="text-xs text-slate-400">Service Due</p>
            <p class="mt-1 text-xl font-bold" :class="serviceDueCount ? 'text-gold-400' : 'text-white'">{{ serviceDueCount }}</p>
          </button>
          <button
            class="rounded-xl border p-4 text-left transition"
            :class="pendingBookingsCount ? 'border-gold-500 hover:border-gold-400' : 'border-navy-800 hover:border-gold-400'"
            @click="scrollToSection('bookings-section')"
          >
            <p class="text-xs text-slate-400">Awaiting Approval</p>
            <p class="mt-1 text-xl font-bold" :class="pendingBookingsCount ? 'text-gold-400' : 'text-white'">{{ pendingBookingsCount }}</p>
          </button>
          <button
            class="rounded-xl border border-navy-800 bg-navy-900 p-4 text-left transition hover:border-gold-400"
            @click="scrollToSection('bookings-section')"
          >
            <p class="text-xs text-slate-400">Active Trips</p>
            <p class="mt-1 text-xl font-bold text-white">{{ activeTripsCount }}</p>
          </button>
          <button
            class="rounded-xl border border-navy-800 bg-navy-900 p-4 text-left transition hover:border-gold-400"
            @click="scrollToSection('bookings-section')"
          >
            <p class="text-xs text-slate-400">Completed Trips</p>
            <p class="mt-1 text-xl font-bold text-white">{{ completedTripsCount }}</p>
          </button>
        </div>

        <!-- My live vehicles -->
        <section id="vehicles-section" class="mt-10 scroll-mt-6">
          <h2 class="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gold-400">
            <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5 17h14M6 17l1.5-5h9L18 17M9 12V8h6v4M10 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm5 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z" />
            </svg>
            My Vehicles
          </h2>
          <div class="mt-3 space-y-3">
            <div
              v-for="vehicle in profile.vehicles"
              :key="vehicle.id"
              class="rounded-xl border border-navy-800 bg-navy-900 p-4 transition hover:border-navy-700"
            >
              <div class="flex items-center gap-4">
                <div class="h-16 w-24 shrink-0 overflow-hidden rounded-lg border border-navy-800 bg-navy-800">
                  <img v-if="vehicle.image" :src="vehicle.image" :alt="vehicle.name" class="h-full w-full object-cover" />
                  <div v-else class="flex h-full w-full items-center justify-center text-slate-600">
                    <svg class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M5 17h14M6 17l1.5-5h9L18 17M9 12V8h6v4" />
                    </svg>
                  </div>
                </div>
                <div class="flex-1">
                  <p class="font-semibold text-white">{{ vehicle.name }}</p>
                  <p class="text-xs text-slate-400">
                    {{ vehicle.category_name || vehicle.category }} &middot;
                    KES {{ Number(vehicle.price_per_day).toLocaleString() }}/day
                  </p>
                </div>
                <span
                  class="rounded-full px-2.5 py-0.5 text-xs font-semibold"
                  :class="vehicle.is_available ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'"
                >
                  {{ vehicle.is_available ? 'Available' : 'Unavailable' }}
                </span>
              </div>

              <p v-if="vehicle.is_service_due" class="mt-3 flex items-center gap-1.5 rounded-lg bg-gold-500/10 px-3 py-2 text-xs font-semibold text-gold-400">
                <svg class="h-4 w-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                </svg>
                Service due - no service logged in the last 90 days. Log one below.
              </p>

              <!-- Service history -->
              <div class="mt-3 border-t border-navy-800 pt-3">
                <div class="flex items-center justify-between">
                  <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Service History
                    <span v-if="vehicle.service_records?.length" class="text-slate-600">({{ vehicle.service_records.length }})</span>
                  </p>
                  <button
                    v-if="serviceFormVehicleId !== vehicle.id"
                    class="text-xs font-semibold text-gold-400 hover:text-gold-300"
                    @click="openServiceForm(vehicle.id)"
                  >
                    + Log Service
                  </button>
                  <button
                    v-else
                    class="text-xs font-semibold text-slate-400 hover:text-white"
                    @click="serviceFormVehicleId = null"
                  >
                    Cancel
                  </button>
                </div>

                <ul v-if="vehicle.service_records?.length" class="mt-2 space-y-1">
                  <li v-for="record in vehicle.service_records" :key="record.id" class="text-xs text-slate-400">
                    <span class="text-slate-300">{{ record.service_date }}</span>
                    <span v-if="record.notes"> &middot; {{ record.notes }}</span>
                  </li>
                </ul>
                <p v-else-if="serviceFormVehicleId !== vehicle.id" class="mt-2 text-xs text-slate-600">
                  No service logged yet.
                </p>

                <form
                  v-if="serviceFormVehicleId === vehicle.id"
                  class="mt-2 space-y-2 rounded-lg bg-navy-950 p-3"
                  @submit.prevent="logService(vehicle)"
                >
                  <p v-if="serviceError" class="text-xs text-red-400">{{ serviceError }}</p>
                  <div class="flex gap-2">
                    <input
                      v-model="serviceDateDraft" type="date" required
                      class="rounded-md border border-navy-700 bg-navy-800 px-2 py-1.5 text-xs text-white focus:border-gold-500 focus:outline-none"
                    />
                    <input
                      v-model="serviceNotesDraft" type="text" placeholder="e.g. Oil change + filter"
                      class="flex-1 rounded-md border border-navy-700 bg-navy-800 px-2 py-1.5 text-xs text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                    />
                  </div>
                  <button
                    type="submit"
                    :disabled="loggingServiceId === vehicle.id"
                    class="rounded-md bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                  >
                    {{ loggingServiceId === vehicle.id ? 'Saving...' : 'Save' }}
                  </button>
                </form>
              </div>
            </div>
            <p v-if="!profile.vehicles.length" class="text-sm text-slate-500">No live vehicles yet.</p>
          </div>
        </section>

        <!-- My bookings -->
        <section id="bookings-section" class="mt-10 scroll-mt-6">
          <h2 class="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gold-400">
            <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 3v4M16 3v4M4 9h16M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z" />
            </svg>
            My Bookings
          </h2>
          <p class="mt-1 text-xs text-slate-500">
            Trips customers have booked with you online - approve a new one to let us know you've seen it.
          </p>

          <p v-if="bookingsError" class="mt-3 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ bookingsError }}</p>

          <div class="mt-3 space-y-3">
            <div
              v-for="booking in bookings"
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
                <button
                  v-else
                  :disabled="acknowledgingId === booking.id"
                  class="mr-auto rounded-md bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                  @click="acknowledgeBooking(booking)"
                >
                  {{ acknowledgingId === booking.id ? 'Approving...' : 'Approve' }}
                </button>

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
              <p
                v-if="booking.trip_ended_at && !['completed', 'cancelled'].includes(booking.status)"
                class="mt-2 text-xs font-semibold text-amber-400"
              >
                Vehicle returned - awaiting final payment (KES {{ Number(booking.balance_due).toLocaleString() }}) to complete.
              </p>

              <!-- Collect payment: declare (client's chosen method + exact amount), then confirm once actually received -->
              <div
                v-if="booking.status !== 'cancelled' && (booking.pending_payments?.length || Number(booking.balance_due) > 0)"
                class="mt-3 border-t border-navy-800 pt-3"
              >
                <div v-if="booking.pending_payments?.length" class="space-y-2">
                  <div
                    v-for="payment in booking.pending_payments" :key="payment.id"
                    class="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-gold-500/10 p-3"
                  >
                    <p class="text-xs font-semibold text-gold-400">
                      KES {{ Number(payment.amount).toLocaleString() }} declared via
                      {{ payment.method === 'mpesa' ? 'M-Pesa' : payment.method === 'card' ? 'card' : 'cash' }} -
                      confirm once actually received.
                    </p>
                    <button
                      :disabled="confirmingPaymentId === payment.id"
                      class="shrink-0 rounded-md bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                      @click="confirmPayment(booking, payment)"
                    >
                      {{ confirmingPaymentId === payment.id ? 'Confirming...' : 'Confirm Received' }}
                    </button>
                  </div>
                  <p v-if="confirmError" class="text-xs text-red-400">{{ confirmError }}</p>
                </div>

                <div v-if="Number(booking.balance_due) > 0" class="mt-2">
                  <button
                    v-if="paymentFormBookingId !== booking.id"
                    class="text-xs font-semibold text-gold-400 hover:text-gold-300"
                    @click="openPaymentForm(booking)"
                  >
                    + Collect Payment (KES {{ Number(booking.balance_due).toLocaleString() }} owed)
                  </button>
                  <template v-else>
                    <div class="flex items-center justify-between">
                      <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Collect Payment</p>
                      <button class="text-xs font-semibold text-slate-400 hover:text-white" @click="paymentFormBookingId = null">
                        Cancel
                      </button>
                    </div>
                    <form class="mt-2 space-y-2" @submit.prevent="declarePayment(booking)">
                      <p v-if="declareError" class="text-xs text-red-400">{{ declareError }}</p>
                      <div class="grid grid-cols-3 gap-2">
                        <button
                          v-for="opt in ['cash', 'card', 'mpesa']" :key="opt" type="button"
                          class="rounded-md border px-2 py-1.5 text-xs font-semibold capitalize"
                          :class="paymentMethodDraft === opt ? 'border-gold-500 bg-gold-500 text-navy-950' : 'border-navy-700 text-slate-300'"
                          @click="paymentMethodDraft = opt"
                        >
                          {{ opt === 'mpesa' ? 'M-Pesa' : opt }}
                        </button>
                      </div>
                      <input
                        v-model="paymentAmountDraft" type="number" min="0" step="0.01" placeholder="Amount" required
                        class="w-full rounded-md border border-navy-700 bg-navy-800 px-2 py-1.5 text-xs text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                      />
                      <button
                        type="submit"
                        :disabled="declaringPaymentId === booking.id"
                        class="w-full rounded-md bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                      >
                        {{
                          declaringPaymentId === booking.id ? 'Saving...'
                            : paymentMethodDraft === 'mpesa' ? 'Send M-Pesa Prompt' : 'Declare Payment'
                        }}
                      </button>
                    </form>
                  </template>
                </div>
              </div>

              <!-- Cash deposits owed to the Paybill -->
              <div v-if="booking.pending_cash_deposits?.length" class="mt-3 space-y-2 border-t border-navy-800 pt-3">
                <div v-for="payment in booking.pending_cash_deposits" :key="payment.id" class="rounded-lg bg-gold-500/10 p-3">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <p class="text-xs font-semibold text-gold-400">
                      KES {{ Number(payment.amount).toLocaleString() }} collected in cash - deposit this to Paybill
                      400400 (Acc: SILVERLAKE) and log it below.
                    </p>
                    <button
                      v-if="depositFormPaymentId !== payment.id"
                      class="shrink-0 text-xs font-semibold text-gold-400 hover:text-gold-300"
                      @click="openDepositForm(payment)"
                    >
                      Log Deposit
                    </button>
                    <button
                      v-else
                      class="shrink-0 text-xs font-semibold text-slate-400 hover:text-white"
                      @click="depositFormPaymentId = null"
                    >
                      Cancel
                    </button>
                  </div>
                  <form
                    v-if="depositFormPaymentId === payment.id"
                    class="mt-2 space-y-2"
                    @submit.prevent="logCashDeposit(booking, payment)"
                  >
                    <p v-if="depositError" class="text-xs text-red-400">{{ depositError }}</p>
                    <div class="flex flex-wrap gap-2">
                      <input
                        v-model="depositAmountDraft" type="number" min="0" step="0.01" placeholder="Amount deposited" required
                        class="w-36 rounded-md border border-navy-700 bg-navy-800 px-2 py-1.5 text-xs text-white focus:border-gold-500 focus:outline-none"
                      />
                      <input
                        v-model="depositReferenceDraft" type="text" placeholder="M-Pesa reference (e.g. QWE123RTY)" required
                        class="flex-1 rounded-md border border-navy-700 bg-navy-800 px-2 py-1.5 text-xs text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                      />
                    </div>
                    <button
                      type="submit"
                      :disabled="loggingDepositId === payment.id"
                      class="rounded-md bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                    >
                      {{ loggingDepositId === payment.id ? 'Saving...' : 'Confirm Deposit' }}
                    </button>
                  </form>
                </div>
              </div>
            </div>
            <p v-if="!bookingsLoading && !bookings.length" class="text-sm text-slate-500">No bookings yet.</p>
          </div>
        </section>

        <!-- Walk-up client booking -->
        <section id="walkup-section" class="mt-10 scroll-mt-6">
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
              v-if="profile.vehicles.length"
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

        <!-- Vehicle submissions -->
        <section id="submissions-section" class="mt-10 scroll-mt-6">
          <div class="flex items-center justify-between">
            <h2 class="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gold-400">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H6a2 2 0 01-2-2V6Z" />
              </svg>
              My Vehicle Submissions
            </h2>
            <button
              class="flex items-center gap-2 rounded-lg bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 transition hover:bg-gold-400"
              @click="openModal"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              Add a Car
            </button>
          </div>
          <p class="mt-1 text-xs text-slate-500">
            New cars go live once an admin reviews and approves them.
          </p>

          <div class="mt-3 space-y-3">
            <div
              v-for="submission in profile.vehicle_submissions"
              :key="submission.id"
              class="rounded-xl border border-navy-800 bg-navy-900 p-4 transition hover:border-navy-700"
            >
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="font-semibold text-white">{{ submission.name }}</p>
                  <p class="text-xs text-slate-400">
                    {{ submission.category_name || submission.category }} &middot;
                    KES {{ Number(submission.price_per_day).toLocaleString() }}/day
                  </p>
                </div>
                <span
                  class="rounded-full px-2.5 py-0.5 text-xs font-semibold"
                  :class="{
                    'bg-gold-500/10 text-gold-400': submission.status === 'pending',
                    'bg-emerald-500/10 text-emerald-400': submission.status === 'approved',
                    'bg-red-500/10 text-red-400': submission.status === 'rejected',
                  }"
                >
                  {{ submission.status }}
                </span>
              </div>
              <p v-if="submission.status === 'rejected' && submission.review_notes" class="mt-2 text-xs text-red-400">
                {{ submission.review_notes }}
              </p>
            </div>
            <p v-if="!profile.vehicle_submissions.length" class="text-sm text-slate-500">No submissions yet.</p>
          </div>
        </section>
      </template>
    </main>

    <!-- Walk-Up Client Booking Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showOnsiteModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showOnsiteModal = false"
        >
          <div class="w-full max-w-lg rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">
                {{ onsiteResult ? 'Booking Created' : 'Book For a Client On-Site' }}
              </h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showOnsiteModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <!-- Result: collect payment (method + exact amount), fall back to sharing the link -->
            <div v-if="onsiteResult" class="space-y-4">
              <p class="text-sm text-slate-300">
                Booking created for <strong>{{ onsiteResult.booking.customer_name }}</strong>.
                Ask how they're paying and the exact amount.
              </p>

              <div v-if="onsiteResult.booking.pending_payments?.length" class="space-y-2">
                <div
                  v-for="payment in onsiteResult.booking.pending_payments" :key="payment.id"
                  class="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-gold-500/10 p-3"
                >
                  <p class="text-xs font-semibold text-gold-400">
                    KES {{ Number(payment.amount).toLocaleString() }} declared via
                    {{ payment.method === 'mpesa' ? 'M-Pesa' : payment.method === 'card' ? 'card' : 'cash' }} -
                    confirm once actually received.
                  </p>
                  <button
                    :disabled="confirmingPaymentId === payment.id"
                    class="shrink-0 rounded-md bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                    @click="confirmPayment(onsiteResult.booking, payment)"
                  >
                    {{ confirmingPaymentId === payment.id ? 'Confirming...' : 'Confirm Received' }}
                  </button>
                </div>
                <p v-if="confirmError" class="text-xs text-red-400">{{ confirmError }}</p>
              </div>

              <div v-if="Number(onsiteResult.booking.balance_due) > 0" class="rounded-lg border border-navy-700 bg-navy-800/50 p-4">
                <div v-if="paymentFormBookingId === onsiteResult.booking.id">
                  <p class="text-xs font-semibold uppercase tracking-wide text-gold-400">Collect Payment</p>
                  <form class="mt-2 space-y-2" @submit.prevent="declarePayment(onsiteResult.booking)">
                    <p v-if="declareError" class="text-xs text-red-400">{{ declareError }}</p>
                    <div class="grid grid-cols-3 gap-2">
                      <button
                        v-for="opt in ['cash', 'card', 'mpesa']" :key="opt" type="button"
                        class="rounded-md border px-2 py-1.5 text-xs font-semibold capitalize"
                        :class="paymentMethodDraft === opt ? 'border-gold-500 bg-gold-500 text-navy-950' : 'border-navy-700 text-slate-300'"
                        @click="paymentMethodDraft = opt"
                      >
                        {{ opt === 'mpesa' ? 'M-Pesa' : opt }}
                      </button>
                    </div>
                    <input
                      v-model="paymentAmountDraft" type="number" min="0" step="0.01"
                      :placeholder="`Amount (deposit: KES ${Number(onsiteResult.booking.deposit_amount).toLocaleString()})`"
                      class="w-full rounded-lg border border-navy-700 bg-navy-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                    />
                    <button
                      type="submit"
                      :disabled="declaringPaymentId === onsiteResult.booking.id"
                      class="w-full rounded-lg bg-gold-500 py-2 text-sm font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                    >
                      {{
                        declaringPaymentId === onsiteResult.booking.id ? 'Saving...'
                          : paymentMethodDraft === 'mpesa' ? 'Send M-Pesa Prompt' : 'Declare Payment'
                      }}
                    </button>
                  </form>
                </div>
                <button
                  v-else
                  class="text-xs font-semibold text-gold-400 hover:text-gold-300"
                  @click="openPaymentForm(onsiteResult.booking)"
                >
                  + Collect Payment
                </button>
              </div>

              <details class="text-sm text-slate-400">
                <summary class="cursor-pointer select-none font-semibold text-slate-300">
                  Or share a payment link instead
                </summary>
                <div class="mt-2 flex items-center gap-2 rounded-lg border border-navy-700 bg-navy-800 px-3 py-2">
                  <span class="flex-1 truncate text-xs text-slate-300">{{ onsiteResult.payment_url }}</span>
                  <button
                    class="shrink-0 rounded-md bg-gold-500 px-3 py-1 text-xs font-semibold text-navy-950 hover:bg-gold-400"
                    @click="copyPaymentLink"
                  >
                    Copy
                  </button>
                </div>
                <a
                  :href="`https://wa.me/?text=${encodeURIComponent('Here is your SilverLake payment link: ' + onsiteResult.payment_url)}`"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="mt-2 flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-500 py-2.5 text-sm font-semibold text-emerald-400 hover:bg-emerald-500 hover:text-navy-950"
                >
                  Share via WhatsApp
                </a>
              </details>

              <button
                class="w-full rounded-lg border border-navy-700 py-2.5 text-sm font-semibold text-slate-300 hover:border-slate-500 hover:text-white"
                @click="showOnsiteModal = false"
              >
                Done
              </button>
            </div>

            <!-- Form -->
            <form v-else class="space-y-4" @submit.prevent="submitOnsiteBooking">
              <p v-if="onsiteError" class="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ onsiteError }}</p>

              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Vehicle *</label>
                <select
                  v-model.number="onsiteForm.vehicle" required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                >
                  <option value="" disabled>Select one of your vehicles</option>
                  <option v-for="v in profile.vehicles" :key="v.id" :value="v.id">{{ v.name }}</option>
                </select>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Client Name *</label>
                  <input v-model="onsiteForm.customer_name" type="text" required
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Phone *</label>
                  <input v-model="onsiteForm.customer_phone" type="tel" placeholder="2547XXXXXXXX" required
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                </div>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Email (optional)</label>
                <input v-model="onsiteForm.customer_email" type="email"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Start Date *</label>
                  <input v-model="onsiteForm.start_date" type="date" :min="today" required
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">End Date *</label>
                  <input v-model="onsiteForm.end_date" type="date" :min="onsiteForm.start_date || today" required
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                  />
                </div>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Pickup Location *</label>
                <input v-model="onsiteForm.pickup_location" type="text" required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Drop-off Location (optional)</label>
                <input v-model="onsiteForm.dropoff_location" type="text"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                />
              </div>

              <div class="flex gap-3 pt-2">
                <button type="button"
                  class="flex-1 rounded-lg border border-navy-700 py-2.5 text-sm font-semibold text-slate-300 hover:border-slate-500 hover:text-white"
                  @click="showOnsiteModal = false">
                  Cancel
                </button>
                <button type="submit" :disabled="onsiteSaving"
                  class="flex-1 rounded-lg bg-gold-500 py-2.5 text-sm font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50">
                  {{ onsiteSaving ? 'Creating…' : 'Create Booking' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Add Vehicle Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-lg rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">Add a Car</h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ formError }}</p>

            <form class="space-y-4" @submit.prevent="submitVehicle">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Vehicle Name *</label>
                <input
                  v-model="form.name" type="text" placeholder="Toyota Prado TZG" required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Category</label>
                  <select v-model="form.category"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none">
                    <option v-for="cat in categories" :key="cat.slug" :value="cat.slug">{{ cat.name }}</option>
                  </select>
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Capacity (pax)</label>
                  <input v-model="form.passenger_capacity" type="number" min="1" max="50"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                  />
                </div>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Price / Day (KES) *</label>
                <input v-model="form.price_per_day" type="number" min="0" step="0.01" placeholder="15000" required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Description</label>
                <textarea v-model="form.description" rows="2"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                ></textarea>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">
                  Vehicle Photos * <span class="normal-case text-slate-500">(at least 2)</span>
                </label>
                <input type="file" accept="image/*" multiple required
                  class="w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
                  @change="onPhotosSelected"
                />
                <div v-if="photoPreviewUrls.length" class="mt-2 flex flex-wrap gap-2">
                  <img
                    v-for="(url, i) in photoPreviewUrls" :key="i" :src="url" alt="Preview"
                    class="h-16 w-24 rounded-lg border border-navy-700 object-cover"
                  />
                </div>
                <p v-if="photoFiles.length && photoFiles.length < 2" class="mt-1 text-xs text-red-400">
                  Add at least one more photo.
                </p>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Logbook / Ownership Document *</label>
                <input type="file" accept="image/*,.pdf" required
                  class="w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
                  @change="logbookFile = $event.target.files[0]"
                />
              </div>

              <div class="flex gap-3 pt-2">
                <button type="button"
                  class="flex-1 rounded-lg border border-navy-700 py-2.5 text-sm font-semibold text-slate-300 hover:border-slate-500 hover:text-white"
                  @click="showModal = false">
                  Cancel
                </button>
                <button type="submit" :disabled="saving"
                  class="flex-1 rounded-lg bg-gold-500 py-2.5 text-sm font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50">
                  {{ saving ? 'Submitting…' : 'Submit for Review' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active { transition: opacity 0.2s ease; }
.modal-fade-enter-from,
.modal-fade-leave-to { opacity: 0; }
</style>
