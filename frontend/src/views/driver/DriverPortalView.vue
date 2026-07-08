<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const router = useRouter()

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
  cashAmount.value = ''
  cashNote.value = ''
  cashError.value = ''
  cashRecorded.value = false
  showOnsiteModal.value = true
}

async function submitOnsiteBooking() {
  onsiteError.value = ''
  onsiteSaving.value = true
  try {
    const { data } = await apiClient.post('/driver/bookings/create/', onsiteForm)
    onsiteResult.value = data
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

// ── Cash payment for the just-created walk-up booking ───────────────────────
const cashAmount = ref('')
const cashNote = ref('')
const cashSaving = ref(false)
const cashError = ref('')
const cashRecorded = ref(false)

async function recordCashPayment() {
  cashError.value = ''
  if (!cashAmount.value) return
  cashSaving.value = true
  try {
    const { data } = await apiClient.post(
      `/driver/bookings/${onsiteResult.value.booking.id}/record-cash/`,
      { amount: cashAmount.value, note: cashNote.value },
    )
    onsiteResult.value.booking = data
    cashRecorded.value = true
  } catch (err) {
    cashError.value = err?.response?.data?.detail || 'Could not record this payment.'
  } finally {
    cashSaving.value = false
  }
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
      <div>
        <h1 class="font-[Georgia] text-lg font-bold text-white">Driver Portal</h1>
        <p class="text-xs text-slate-400">SilverLake Car Rentals</p>
      </div>
      <div class="flex items-center gap-4">
        <RouterLink to="/" class="text-sm font-medium text-slate-300 hover:text-gold-400">Back to Site</RouterLink>
        <button class="text-sm font-medium text-slate-300 hover:text-gold-400" @click="handleLogout">Log Out</button>
      </div>
    </header>

    <main class="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <p v-if="loading" class="text-center text-slate-400">Loading...</p>
      <p v-else-if="error" class="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ error }}</p>

      <template v-else-if="profile">
        <!-- Profile + availability card -->
        <section class="rounded-2xl border border-navy-800 bg-navy-900 p-6">
          <div class="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 class="font-[Georgia] text-xl font-bold text-white">{{ profile.full_name }}</h2>
              <p class="text-sm text-slate-400">
                {{ profile.years_of_experience }} years experience &middot; Rating {{ Number(profile.rating).toFixed(1) }}
              </p>
            </div>
            <span
              class="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold"
              :class="profile.is_away ? 'bg-red-500/10 text-red-400' : 'bg-emerald-500/10 text-emerald-400'"
            >
              <span class="h-1.5 w-1.5 rounded-full" :class="profile.is_away ? 'bg-red-400' : 'bg-emerald-400'" />
              {{ profile.is_away ? 'Away' : 'Available' }}
            </span>
          </div>

          <p v-if="profile.is_away && profile.away_reason" class="mt-3 rounded-lg bg-navy-800 px-4 py-3 text-sm text-slate-300">
            <span class="font-semibold text-slate-400">Your reason: </span>{{ profile.away_reason }}
          </p>
          <p class="mt-3 text-xs text-slate-500">
            While marked away, your vehicle(s) won't show up in the public fleet for customers to book.
            Admins can still see your reason.
          </p>

          <div class="mt-4">
            <button
              v-if="!profile.is_away && !showAwayForm"
              class="rounded-md border border-red-400 px-4 py-2 text-sm font-semibold text-red-400 hover:bg-red-400 hover:text-navy-950"
              @click="openAwayForm"
            >
              Mark Myself Away
            </button>
            <button
              v-else-if="profile.is_away"
              :disabled="awaySaving"
              class="rounded-md bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
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

        <!-- My live vehicles -->
        <section class="mt-8">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">My Vehicles</h2>
          <div class="mt-3 space-y-3">
            <div
              v-for="vehicle in profile.vehicles"
              :key="vehicle.id"
              class="flex items-center gap-4 rounded-xl border border-navy-800 bg-navy-900 p-4"
            >
              <div class="h-14 w-20 shrink-0 overflow-hidden rounded-lg border border-navy-800 bg-navy-800">
                <img v-if="vehicle.image" :src="vehicle.image" :alt="vehicle.name" class="h-full w-full object-cover" />
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
            <p v-if="!profile.vehicles.length" class="text-sm text-slate-500">No live vehicles yet.</p>
          </div>
        </section>

        <!-- My bookings -->
        <section class="mt-8">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">My Bookings</h2>
          <p class="mt-1 text-xs text-slate-500">
            Trips customers have booked with you online - approve a new one to let us know you've seen it.
          </p>

          <p v-if="bookingsError" class="mt-3 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ bookingsError }}</p>

          <div class="mt-3 space-y-3">
            <div
              v-for="booking in bookings"
              :key="booking.id"
              class="rounded-xl border p-4"
              :class="!booking.driver_acknowledged_at ? 'border-gold-500 bg-navy-900' : 'border-navy-800 bg-navy-900'"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="font-semibold text-white">{{ booking.customer_name }}</p>
                  <p class="text-xs text-slate-400">
                    {{ booking.vehicle_name }} &middot; {{ booking.start_date }} to {{ booking.end_date }}
                  </p>
                  <p class="text-xs text-slate-500">{{ booking.pickup_location }}</p>
                </div>
                <span
                  class="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold"
                  :class="statusClasses[booking.status]"
                >
                  {{ statusLabels[booking.status] || booking.status }}
                </span>
              </div>
              <div class="mt-3 flex items-center justify-between gap-3">
                <span v-if="booking.driver_acknowledged_at" class="text-xs font-semibold text-emerald-400">
                  Acknowledged
                </span>
                <button
                  v-else
                  :disabled="acknowledgingId === booking.id"
                  class="rounded-md bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                  @click="acknowledgeBooking(booking)"
                >
                  {{ acknowledgingId === booking.id ? 'Approving...' : 'Approve' }}
                </button>

                <button
                  v-if="['confirmed', 'ongoing'].includes(booking.status)"
                  :disabled="completingId === booking.id"
                  class="rounded-md border border-navy-700 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                  @click="completeBooking(booking)"
                >
                  {{ completingId === booking.id ? 'Completing...' : 'Complete Trip' }}
                </button>
              </div>
            </div>
            <p v-if="!bookingsLoading && !bookings.length" class="text-sm text-slate-500">No bookings yet.</p>
          </div>
        </section>

        <!-- Walk-up client booking -->
        <section class="mt-8">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Walk-Up Client</h2>
            <button
              v-if="profile.vehicles.length"
              class="flex items-center gap-2 rounded-lg bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400"
              @click="openOnsiteModal"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              Book For a Client On-Site
            </button>
          </div>
          <p class="mt-1 text-xs text-slate-500">
            For a client with you right now who doesn't want to register - creates their booking and
            gives you a payment link to share, no account needed on their end.
          </p>
        </section>

        <!-- Vehicle submissions -->
        <section class="mt-8">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">My Vehicle Submissions</h2>
            <button
              class="flex items-center gap-2 rounded-lg bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400"
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
              class="rounded-xl border border-navy-800 bg-navy-900 p-4"
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

            <!-- Result: payment link + cash option -->
            <div v-if="onsiteResult" class="space-y-4">
              <p class="text-sm text-slate-300">
                Booking created for <strong>{{ onsiteResult.booking.customer_name }}</strong>. Share this link so
                they can pay via M-Pesa on their own phone - no account needed.
              </p>
              <div class="flex items-center gap-2 rounded-lg border border-navy-700 bg-navy-800 px-3 py-2">
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
                class="flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-500 py-2.5 text-sm font-semibold text-emerald-400 hover:bg-emerald-500 hover:text-navy-950"
              >
                Share via WhatsApp
              </a>

              <div class="rounded-lg border border-navy-700 bg-navy-800/50 p-4">
                <p class="text-xs font-semibold uppercase tracking-wide text-gold-400">Client Paid Cash Instead?</p>
                <div v-if="cashRecorded" class="mt-2 text-sm text-emerald-400">Cash payment recorded.</div>
                <div v-else class="mt-2 space-y-2">
                  <input
                    v-model="cashAmount" type="number" min="0" step="0.01"
                    :placeholder="`Amount (deposit: KES ${Number(onsiteResult.booking.deposit_amount).toLocaleString()})`"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                  <input
                    v-model="cashNote" type="text" placeholder="Note (optional)"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                  <p v-if="cashError" class="text-xs text-red-400">{{ cashError }}</p>
                  <button
                    :disabled="cashSaving || !cashAmount"
                    class="w-full rounded-lg bg-navy-700 py-2 text-sm font-semibold text-white hover:bg-navy-600 disabled:opacity-50"
                    @click="recordCashPayment"
                  >
                    {{ cashSaving ? 'Recording...' : 'Record Cash Payment' }}
                  </button>
                </div>
              </div>

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
