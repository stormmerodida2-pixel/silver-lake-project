<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import apiClient from '../api/client'
import AvailabilityCalendar from '../components/AvailabilityCalendar.vue'
import PhoneInput from '../components/PhoneInput.vue'
import { useAuthStore } from '../stores/auth'
import { useCatalogStore } from '../stores/catalog'
import { trackEvent } from '../utils/analytics'

const route = useRoute()
const catalog = useCatalogStore()
const auth = useAuthStore()

const form = reactive({
  vehicle: route.query.vehicle ? Number(route.query.vehicle) : '',
  service_type: route.query.service || 'with_driver',
  customer_name: auth.user ? `${auth.user.first_name} ${auth.user.last_name}`.trim() : '',
  customer_phone: auth.user?.phone_number || '',
  customer_email: auth.user?.email || '',
  pickup_location: route.query.pickup || '',
  dropoff_location: route.query.dropoff || '',
  start_date: '',
  end_date: '',
  notes: '',
  customer_license_number: '',
  discount_code: '',
})

// ── Booking for someone else ─────────────────────────────────────────────────
// customer_name/phone/email have always been independent of the account's own info (the
// backend never assumed they matched - see BookingViewSet.perform_create, which always sets
// booking.user=request.user regardless of these fields) - this just makes that possibility
// visible in the UI instead of it only working if you happened to overwrite the prefilled values.
const bookingFor = ref('myself') // 'myself' | 'someone_else'
const ownName = auth.user ? `${auth.user.first_name} ${auth.user.last_name}`.trim() : ''
const ownPhone = auth.user?.phone_number || ''
const ownEmail = auth.user?.email || ''

watch(bookingFor, (value) => {
  if (value === 'myself') {
    form.customer_name = ownName
    form.customer_phone = ownPhone
    form.customer_email = ownEmail
  } else {
    form.customer_name = ''
    form.customer_phone = ''
    form.customer_email = ''
  }
})

// The M-Pesa prompt always goes to whoever is actually paying (the account holder), never to
// the rider's own contact number above - those are two different people when bookingFor is
// 'someone_else', and even when booking for yourself this is just clearer as its own field
// than silently reusing the trip-contact phone for payment too.
const paymentPhone = ref(ownPhone)

const licenseDocument = ref(null)
const idDocument = ref(null)

const paymentMethod = ref('mpesa')
const payOption = ref('deposit') // 'deposit' | 'full'
const step = ref('form') // form -> confirmed -> paying
const booking = ref(null)
const submitting = ref(false)
const error = ref('')
const today = new Date().toISOString().split('T')[0]

// ── Referral credit ──────────────────────────────────────────────────────────
const referralCreditBalance = ref(0)
const applyingCredit = ref(false)
const creditError = ref('')

async function refreshReferralCreditBalance() {
  if (!auth.isAuthenticated) return
  try {
    const { data } = await apiClient.get('/auth/me/')
    referralCreditBalance.value = data.referral_credit_balance
  } catch (err) {
    // Advisory only - the "Apply Credit" button just won't show if this fails.
  }
}

async function applyReferralCredit() {
  applyingCredit.value = true
  creditError.value = ''
  try {
    await apiClient.post('/payments/referral-credit/redeem/', { booking: booking.value.id })
    const { data } = await apiClient.get(`/bookings/${booking.value.id}/`)
    booking.value = data
    await refreshReferralCreditBalance()
  } catch (err) {
    creditError.value = err.response?.data?.detail || 'Could not apply your referral credit.'
  } finally {
    applyingCredit.value = false
  }
}

// ── Card form (UI only - no gateway wired up yet, nothing here is ever sent anywhere) ──────
const card = reactive({ number: '', name: '', expiry: '', cvv: '' })
const cardNotice = ref('')

function onCardNumberInput(event) {
  const digits = event.target.value.replace(/\D/g, '').slice(0, 16)
  card.number = digits.replace(/(.{4})/g, '$1 ').trim()
}

function onCardExpiryInput(event) {
  const digits = event.target.value.replace(/\D/g, '').slice(0, 4)
  card.expiry = digits.length > 2 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits
}

function onCardCvvInput(event) {
  card.cvv = event.target.value.replace(/\D/g, '').slice(0, 4)
}

function submitCardPayment() {
  // There's no card gateway wired up yet - deliberately not sending these details anywhere.
  // Raw card numbers should only ever go straight to a PCI-compliant processor, never our own
  // server, so this stays a UI-only stub until a real gateway (e.g. Flutterwave/Paystack) is
  // integrated.
  cardNotice.value = "Card payments aren't live yet - please use M-Pesa, or reach us on WhatsApp to arrange payment."
}

onMounted(() => {
  catalog.fetchVehicles()
})

// Only offer vehicles that actually support the chosen service type.
const availableVehicles = computed(() =>
  catalog.vehicles.filter((v) =>
    form.service_type === 'with_driver' ? v.allow_with_driver : v.allow_self_drive
  )
)

// If the current service type no longer supports the selected vehicle, clear it.
watch(
  () => form.service_type,
  () => {
    if (form.vehicle && !availableVehicles.value.some((v) => v.id === form.vehicle)) {
      form.vehicle = ''
    }
  }
)

const selectedVehicle = computed(() => catalog.vehicles.find((v) => v.id === form.vehicle))

// ── Availability conflict warning ────────────────────────────────────────────
// Purely advisory - Booking.clean() on the backend is still the real, authoritative check.
// This just saves a wasted round trip by catching an obvious overlap before submit.
const bookedRanges = ref([])

watch(
  () => form.vehicle,
  async (vehicleId) => {
    bookedRanges.value = []
    if (!vehicleId) return
    try {
      const { data } = await apiClient.get(`/vehicles/${vehicleId}/availability/`)
      bookedRanges.value = data
    } catch (err) {
      // Advisory only - if this fails, the form still works, submit just won't warn early.
    }
  },
  { immediate: true }
)

const dateConflictWarning = computed(() => {
  if (!form.start_date || !form.end_date) return ''
  const conflict = bookedRanges.value.some(
    (range) => form.start_date <= range.end_date && form.end_date >= range.start_date
  )
  return conflict
    ? "Heads up - this vehicle already has a booking that overlaps these dates. You can still submit, but it likely won't be accepted."
    : ''
})

// ── Waitlist for fully-booked dates ──────────────────────────────────────────
const joiningWaitlist = ref(false)
const waitlistError = ref('')
const onWaitlistFor = ref(null) // { vehicle, start_date, end_date } once joined for the current selection

// A fresh vehicle/date pick always needs a fresh join - never assume yesterday's confirmation
// still applies to today's selection.
watch([() => form.vehicle, () => form.start_date, () => form.end_date], () => {
  onWaitlistFor.value = null
  waitlistError.value = ''
})

async function joinWaitlist() {
  joiningWaitlist.value = true
  waitlistError.value = ''
  try {
    await apiClient.post(`/vehicles/${form.vehicle}/waitlist/`, {
      start_date: form.start_date,
      end_date: form.end_date,
    })
    onWaitlistFor.value = { vehicle: form.vehicle, start_date: form.start_date, end_date: form.end_date }
  } catch (err) {
    waitlistError.value = err.response?.data?.detail || 'Could not join the waitlist for this vehicle.'
  } finally {
    joiningWaitlist.value = false
  }
}

async function leaveWaitlist() {
  joiningWaitlist.value = true
  try {
    await apiClient.delete(`/vehicles/${form.vehicle}/waitlist/`, {
      data: { start_date: form.start_date, end_date: form.end_date },
    })
    onWaitlistFor.value = null
  } catch (err) {
    waitlistError.value = 'Could not leave the waitlist.'
  } finally {
    joiningWaitlist.value = false
  }
}

// Keep the layout shape stable while filling the form (no shifting as fields fill in) -
// only the confirmation/payment steps (which have no live sidebar use) switch to a centered column.
const showTwoColumn = computed(() => step.value === 'form')
const showSidebarContent = computed(() => !!selectedVehicle.value)
// The sidebar itself only appears once there's something to show in it - no empty
// placeholder box while the form step is still waiting on a vehicle pick.
const showSidebar = computed(() => showTwoColumn.value && showSidebarContent.value)

// Combine the cover photo with any gallery images so the sidebar can flip through all of them.
const vehiclePhotos = computed(() => {
  const vehicle = selectedVehicle.value
  if (!vehicle) return []
  const photos = []
  if (vehicle.image) photos.push({ image: vehicle.image, caption: vehicle.name })
  for (const g of vehicle.gallery_images || []) photos.push(g)
  return photos
})

const photoIndex = ref(0)
let photoTimer = null

function stopPhotoTimer() {
  clearInterval(photoTimer)
  photoTimer = null
}

// Auto-advances through the gallery when there's more than one photo - restarted after any
// manual interaction so a click doesn't get immediately undone by the next auto-tick.
function startPhotoTimer() {
  stopPhotoTimer()
  if (vehiclePhotos.value.length > 1) {
    photoTimer = setInterval(() => {
      photoIndex.value = (photoIndex.value + 1) % vehiclePhotos.value.length
    }, 4000)
  }
}

watch(selectedVehicle, () => {
  photoIndex.value = 0
  startPhotoTimer()
})

onUnmounted(stopPhotoTimer)

function prevPhoto() {
  photoIndex.value = (photoIndex.value - 1 + vehiclePhotos.value.length) % vehiclePhotos.value.length
  startPhotoTimer()
}

function nextPhoto() {
  photoIndex.value = (photoIndex.value + 1) % vehiclePhotos.value.length
  startPhotoTimer()
}

function goToPhoto(index) {
  photoIndex.value = index
  startPhotoTimer()
}

const totalDays = computed(() => {
  if (!form.start_date || !form.end_date) return 0
  const diff = (new Date(form.end_date) - new Date(form.start_date)) / (1000 * 60 * 60 * 24)
  return Math.max(1, Math.round(diff) + 1)
})

// Self-drive costs 3% more than the vehicle's own with-driver rate - mirrors Booking.save()'s
// SELF_DRIVE_SURCHARGE_PERCENT on the backend, so the preview shown here matches what actually
// gets charged.
const SELF_DRIVE_SURCHARGE_PERCENT = 3

const baseCost = computed(() => {
  if (!selectedVehicle.value) return 0
  return totalDays.value * Number(selectedVehicle.value.price_per_day)
})

const totalCost = computed(() => {
  if (form.service_type !== 'self_drive') return baseCost.value
  return Math.round(baseCost.value * (1 + SELF_DRIVE_SURCHARGE_PERCENT / 100) * 100) / 100
})

const amountToPay = computed(() => {
  if (!booking.value) return 0
  return payOption.value === 'full' ? Number(booking.value.balance_due) : Number(booking.value.deposit_amount)
})

async function submitBooking() {
  submitting.value = true
  error.value = ''
  try {
    const payload = new FormData()
    Object.entries(form).forEach(([key, value]) => payload.append(key, value))
    if (form.service_type === 'self_drive') {
      payload.append('customer_license_document', licenseDocument.value)
      payload.append('customer_id_document', idDocument.value)
    }

    const { data } = await apiClient.post('/bookings/', payload)
    booking.value = data
    step.value = 'confirmed'
    refreshReferralCreditBalance()
    trackEvent('generate_lead', {
      currency: 'KES', value: Number(data.total_amount),
      items: [{ item_id: String(data.vehicle), item_name: selectedVehicle.value?.name }],
      service_type: form.service_type,
    })
  } catch (err) {
    const data = err.response?.data
    if (data && typeof data === 'object') {
      error.value = Object.entries(data)
        .map(([key, messages]) => {
          const field = key === 'non_field_errors' ? '' : `${key.replace('_', ' ')}: `
          const msg = Array.isArray(messages) ? messages.join(' ') : messages
          return `${field}${msg}`
        })
        .join(' | ')
    } else {
      error.value = 'Something went wrong. Please check the form and try again.'
    }
  } finally {
    submitting.value = false
  }
}

// ── Payment status polling ──────────────────────────────────────────────────
const paymentOutcome = ref(null) // null (waiting) | 'successful' | 'failed' | 'timeout'
let pollTimer = null
let pollAttempts = 0
const MAX_POLL_ATTEMPTS = 30 // ~90s at 3s intervals

function stopPolling() {
  clearInterval(pollTimer)
  pollTimer = null
}

function startPolling(paymentId) {
  pollAttempts = 0
  stopPolling()
  pollTimer = setInterval(async () => {
    pollAttempts += 1
    try {
      const { data } = await apiClient.get(`/payments/${paymentId}/`)
      if (data.status === 'successful') {
        stopPolling()
        paymentOutcome.value = 'successful'
        trackEvent('purchase', {
          transaction_id: String(booking.value.id), currency: 'KES', value: amountToPay.value,
          items: [{ item_id: String(booking.value.vehicle), item_name: selectedVehicle.value?.name }],
        })
      } else if (data.status === 'failed') {
        stopPolling()
        paymentOutcome.value = 'failed'
      } else if (pollAttempts >= MAX_POLL_ATTEMPTS) {
        stopPolling()
        paymentOutcome.value = 'timeout'
      }
    } catch (err) {
      // A transient network hiccup shouldn't end the poll - just try again next tick.
      if (pollAttempts >= MAX_POLL_ATTEMPTS) {
        stopPolling()
        paymentOutcome.value = 'timeout'
      }
    }
  }, 3000)
}

onUnmounted(stopPolling)

async function payWithMpesa() {
  if (!paymentPhone.value) {
    error.value = 'Enter the M-Pesa number to charge.'
    return
  }
  submitting.value = true
  error.value = ''
  try {
    const { data } = await apiClient.post('/payments/mpesa/stk-push/', {
      booking: booking.value.id,
      phone_number: paymentPhone.value,
      amount: amountToPay.value,
    })
    paymentOutcome.value = null
    step.value = 'paying'
    startPolling(data.payment_id)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not start M-Pesa payment. You can also pay via Paybill 400400 (Acc: SILVERLAKE).'
  } finally {
    submitting.value = false
  }
}

function retryPayment() {
  paymentOutcome.value = null
  step.value = 'confirmed'
}
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-5xl px-4 py-12 sm:px-6 sm:py-16">
      <div class="text-center">
        <h1 class="font-[Georgia] text-3xl font-bold text-navy-900 sm:text-4xl">Book Your Ride</h1>
        <p class="mt-2 text-slate-600">Choose your vehicle, dates, and how you'd like to travel.</p>
      </div>

      <div class="mt-10 grid gap-8" :class="showSidebar ? 'lg:grid-cols-3' : 'mx-auto max-w-2xl'">
        <!-- Main column: form / confirmation / payment -->
        <div :class="showSidebar ? 'lg:col-span-2' : ''">
          <form v-if="step === 'form'" class="space-y-5 rounded-2xl border border-slate-200 bg-slate-50 p-6 sm:p-8" @submit.prevent="submitBooking">
            <div>
              <label class="mb-1 block text-sm text-slate-600">Service type</label>
              <div class="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  class="rounded-md border px-3 py-2 text-sm font-semibold transition"
                  :class="form.service_type === 'with_driver' ? 'border-brand-blue-600 bg-brand-blue-600 text-white' : 'border-slate-300 text-slate-600'"
                  @click="form.service_type = 'with_driver'"
                >
                  Book with Driver
                </button>
                <button
                  type="button"
                  class="rounded-md border px-3 py-2 text-sm font-semibold transition"
                  :class="form.service_type === 'self_drive' ? 'border-brand-blue-600 bg-brand-blue-600 text-white' : 'border-slate-300 text-slate-600'"
                  @click="form.service_type = 'self_drive'"
                >
                  Self Drive
                </button>
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm text-slate-600">Vehicle</label>
              <select
                v-model.number="form.vehicle"
                required
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              >
                <option value="" disabled>Select a vehicle</option>
                <option v-for="v in availableVehicles" :key="v.id" :value="v.id">
                  {{ v.name }} - KES {{ Number(v.price_per_day).toLocaleString() }}/day
                </option>
              </select>
              <p v-if="!availableVehicles.length" class="mt-1 text-xs text-slate-500">
                No vehicles currently support this service type.
              </p>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="mb-1 block text-sm text-slate-600">Start date</label>
                <input
                  v-model="form.start_date"
                  type="date"
                  :min="today"
                  required
                  class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm text-slate-600">End date</label>
                <input
                  v-model="form.end_date"
                  type="date"
                  :min="form.start_date || today"
                  required
                  class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
                />
              </div>
            </div>

            <div v-if="dateConflictWarning" class="rounded-lg border border-gold-500/40 bg-gold-500/10 px-3 py-2.5 text-sm text-navy-900">
              <p class="flex items-start gap-2">
                <svg class="mt-0.5 h-4 w-4 shrink-0 text-gold-500" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m0 3.75h.008M10.29 3.86L1.82 18a1.5 1.5 0 001.29 2.25h17.78a1.5 1.5 0 001.29-2.25L13.71 3.86a1.5 1.5 0 00-2.42 0z" />
                </svg>
                <span>{{ dateConflictWarning }}</span>
              </p>

              <div class="mt-2 pl-6">
                <p v-if="onWaitlistFor" class="text-brand-blue-600">
                  You're on the waitlist for these dates - we'll email you if it opens up.
                  <button type="button" :disabled="joiningWaitlist" class="ml-1 font-semibold underline disabled:opacity-60" @click="leaveWaitlist">
                    Leave waitlist
                  </button>
                </p>
                <button
                  v-else
                  type="button"
                  :disabled="joiningWaitlist"
                  class="rounded-md border border-navy-800 px-3 py-1.5 text-sm font-semibold text-navy-900 transition hover:bg-navy-900 hover:text-white disabled:opacity-60"
                  @click="joinWaitlist"
                >
                  {{ joiningWaitlist ? 'Joining...' : 'Notify me if it opens up' }}
                </button>
                <p v-if="waitlistError" class="mt-1 text-red-600">{{ waitlistError }}</p>
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm text-slate-600">Pickup location</label>
              <input
                v-model="form.pickup_location"
                type="text"
                required
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              />
            </div>

            <div>
              <label class="mb-1 block text-sm text-slate-600">Drop-off location (optional)</label>
              <input
                v-model="form.dropoff_location"
                type="text"
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              />
            </div>

            <div>
              <label class="mb-1 block text-sm text-slate-600">Who is this trip for?</label>
              <div class="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1">
                <button
                  type="button"
                  class="rounded-md px-4 py-1.5 text-sm font-semibold transition"
                  :class="bookingFor === 'myself' ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-500 hover:text-navy-900'"
                  @click="bookingFor = 'myself'"
                >
                  Myself
                </button>
                <button
                  type="button"
                  class="rounded-md px-4 py-1.5 text-sm font-semibold transition"
                  :class="bookingFor === 'someone_else' ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-500 hover:text-navy-900'"
                  @click="bookingFor = 'someone_else'"
                >
                  Someone else
                </button>
              </div>
              <p v-if="bookingFor === 'someone_else'" class="mt-1.5 text-xs text-slate-500">
                Enter the rider's details below - the M-Pesa payment step further down still charges your own number.
              </p>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="mb-1 block text-sm text-slate-600">{{ bookingFor === 'someone_else' ? "Rider's name" : 'Your name' }}</label>
                <input
                  v-model="form.customer_name"
                  type="text"
                  required
                  class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm text-slate-600">{{ bookingFor === 'someone_else' ? "Rider's phone" : 'Your phone' }}</label>
                <PhoneInput v-model="form.customer_phone" required />
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm text-slate-600">
                {{ bookingFor === 'someone_else' ? "Rider's email (optional)" : 'Email (optional)' }}
              </label>
              <input
                v-model="form.customer_email"
                type="email"
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              />
            </div>

            <div v-if="form.service_type === 'self_drive'" class="space-y-4 rounded-md border border-brand-blue-500/40 bg-brand-blue-500/5 p-4">
              <p class="text-sm font-semibold text-brand-blue-600">
                Self-drive requires proof of a valid license and ID before we hand over the vehicle.
              </p>
              <div>
                <label class="mb-1 block text-sm text-slate-600">Driving license number</label>
                <input
                  v-model="form.customer_license_number"
                  type="text"
                  required
                  class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm text-slate-600">Driving license document (photo or PDF)</label>
                <input
                  type="file"
                  required
                  accept="image/*,.pdf"
                  class="w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
                  @change="licenseDocument = $event.target.files[0]"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm text-slate-600">National ID or passport copy</label>
                <input
                  type="file"
                  required
                  accept="image/*,.pdf"
                  class="w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
                  @change="idDocument = $event.target.files[0]"
                />
              </div>
            </div>

            <p v-if="error" class="text-sm text-red-600">{{ error }}</p>

            <button
              type="submit"
              :disabled="submitting"
              class="w-full rounded-md bg-gold-500 px-4 py-2.5 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
            >
              {{ submitting ? 'Submitting...' : 'Confirm Booking' }}
            </button>
          </form>

          <div v-else-if="step === 'confirmed'" class="rounded-2xl border border-slate-200 bg-white shadow-sm">
            <!-- Success header -->
            <div class="flex items-start gap-4 border-b border-slate-100 p-6 sm:p-8">
              <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
                <svg class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div>
                <h2 class="font-[Georgia] text-xl font-bold text-navy-900">Booking Received</h2>
                <p class="mt-1 text-sm text-slate-500">
                  Reference <span class="font-mono text-slate-700">#{{ booking?.id }}</span>
                </p>
              </div>
            </div>

            <!-- Receipt summary -->
            <div class="border-b border-slate-100 px-6 py-4 text-sm sm:px-8">
              <div class="flex items-center justify-between py-1.5">
                <span class="text-slate-500">Vehicle</span>
                <span class="font-medium text-navy-900">{{ selectedVehicle?.name }}</span>
              </div>
              <div v-if="Number(booking.discount_amount) > 0" class="flex items-center justify-between py-1.5 text-emerald-600">
                <span>Discount ({{ booking.discount_code_display }})</span>
                <span class="font-medium">- KES {{ Number(booking.discount_amount).toLocaleString() }}</span>
              </div>
              <div class="flex items-center justify-between border-t border-dashed border-slate-200 py-1.5 pt-2.5">
                <span class="font-semibold text-navy-900">Trip Total</span>
                <span class="font-[Georgia] text-lg font-bold text-navy-900">
                  KES {{ Number(booking.total_amount).toLocaleString() }}
                </span>
              </div>
            </div>

            <div class="p-6 sm:p-8">
              <label class="mb-2 block text-sm font-semibold text-navy-900">How much would you like to pay now?</label>
              <div class="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  class="rounded-xl border-2 p-3 text-left transition"
                  :class="payOption === 'deposit' ? 'border-brand-blue-600 bg-brand-blue-50' : 'border-slate-200 hover:border-slate-300'"
                  @click="payOption = 'deposit'"
                >
                  <span class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <span
                      class="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border-2"
                      :class="payOption === 'deposit' ? 'border-brand-blue-600' : 'border-slate-300'"
                    >
                      <span v-if="payOption === 'deposit'" class="h-1.5 w-1.5 rounded-full bg-brand-blue-600" />
                    </span>
                    Deposit (30%)
                  </span>
                  <span class="mt-1 block font-[Georgia] text-lg font-bold text-navy-900">
                    KES {{ Number(booking.deposit_amount).toLocaleString() }}
                  </span>
                </button>
                <button
                  type="button"
                  class="rounded-xl border-2 p-3 text-left transition"
                  :class="payOption === 'full' ? 'border-brand-blue-600 bg-brand-blue-50' : 'border-slate-200 hover:border-slate-300'"
                  @click="payOption = 'full'"
                >
                  <span class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <span
                      class="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border-2"
                      :class="payOption === 'full' ? 'border-brand-blue-600' : 'border-slate-300'"
                    >
                      <span v-if="payOption === 'full'" class="h-1.5 w-1.5 rounded-full bg-brand-blue-600" />
                    </span>
                    Pay in Full
                  </span>
                  <span class="mt-1 block font-[Georgia] text-lg font-bold text-navy-900">
                    KES {{ Number(booking.balance_due).toLocaleString() }}
                  </span>
                </button>
              </div>

              <div
                v-if="referralCreditBalance > 0 && booking.balance_due > 0"
                class="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gold-500/40 bg-gold-500/10 p-4"
              >
                <p class="text-sm text-navy-900">
                  You have <span class="font-bold">KES {{ Number(referralCreditBalance).toLocaleString() }}</span> in referral credit available.
                </p>
                <button
                  type="button"
                  :disabled="applyingCredit"
                  class="shrink-0 rounded-md bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
                  @click="applyReferralCredit"
                >
                  {{ applyingCredit ? 'Applying...' : 'Apply Credit' }}
                </button>
              </div>
              <p v-if="creditError" class="mt-2 text-sm text-red-600">{{ creditError }}</p>

              <label class="mb-2 mt-5 block text-sm font-semibold text-navy-900">Payment method</label>
              <div class="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1">
                <button
                  class="rounded-md px-4 py-1.5 text-sm font-semibold transition"
                  :class="paymentMethod === 'mpesa' ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-500 hover:text-navy-900'"
                  @click="paymentMethod = 'mpesa'"
                >
                  M-Pesa
                </button>
                <button
                  class="rounded-md px-4 py-1.5 text-sm font-semibold transition"
                  :class="paymentMethod === 'card' ? 'bg-white text-navy-900 shadow-sm' : 'text-slate-500 hover:text-navy-900'"
                  @click="paymentMethod = 'card'"
                >
                  Card
                </button>
              </div>

              <div v-if="paymentMethod === 'mpesa'" class="mt-5">
                <label class="mb-1 block text-sm text-slate-600">M-Pesa number to charge</label>
                <PhoneInput v-model="paymentPhone" required />
                <p class="mt-1 text-xs text-slate-500">This is charged to you, the account holder - it doesn't need to match the rider's own phone above.</p>

                <p v-if="error" class="mb-3 mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
                  <svg class="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m0 3.75h.008M10.29 3.86L1.82 18a1.5 1.5 0 001.29 2.25h17.78a1.5 1.5 0 001.29-2.25L13.71 3.86a1.5 1.5 0 00-2.42 0z" />
                  </svg>
                  <span>{{ error }}</span>
                </p>
                <button
                  :disabled="submitting"
                  class="mt-3 w-full rounded-md bg-gold-500 px-4 py-2.5 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
                  @click="payWithMpesa"
                >
                  {{ submitting ? 'Sending prompt...' : `Pay KES ${amountToPay.toLocaleString()} via M-Pesa` }}
                </button>
              </div>

              <form v-else class="mt-5 space-y-3" @submit.prevent="submitCardPayment">
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">Card Number</label>
                  <input
                    :value="card.number"
                    type="text"
                    inputmode="numeric"
                    autocomplete="cc-number"
                    placeholder="1234 5678 9012 3456"
                    maxlength="19"
                    class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono tracking-wide text-navy-900 focus:border-brand-blue-500 focus:outline-none"
                    @input="onCardNumberInput"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">Cardholder Name</label>
                  <input
                    v-model="card.name"
                    type="text"
                    autocomplete="cc-name"
                    placeholder="Jane Doe"
                    class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
                  />
                </div>
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">Expiry</label>
                    <input
                      :value="card.expiry"
                      type="text"
                      inputmode="numeric"
                      autocomplete="cc-exp"
                      placeholder="MM/YY"
                      maxlength="5"
                      class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-navy-900 focus:border-brand-blue-500 focus:outline-none"
                      @input="onCardExpiryInput"
                    />
                  </div>
                  <div>
                    <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">CVV</label>
                    <input
                      :value="card.cvv"
                      type="password"
                      inputmode="numeric"
                      autocomplete="cc-csc"
                      placeholder="123"
                      maxlength="4"
                      class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-navy-900 focus:border-brand-blue-500 focus:outline-none"
                      @input="onCardCvvInput"
                    />
                  </div>
                </div>

                <p v-if="cardNotice" class="flex items-start gap-2 rounded-lg border border-gold-500/40 bg-gold-500/10 px-3 py-2.5 text-sm text-navy-900">
                  <svg class="mt-0.5 h-4 w-4 shrink-0 text-gold-500" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{{ cardNotice }}</span>
                </p>

                <button
                  type="submit"
                  class="w-full rounded-md bg-gold-500 px-4 py-2.5 font-semibold text-navy-950 transition hover:bg-gold-400"
                >
                  Pay KES {{ amountToPay.toLocaleString() }} by Card
                </button>
                <p class="text-center text-xs text-slate-400">Secured payment - your card details are never stored on our servers.</p>
              </form>
            </div>
          </div>

          <div v-else-if="step === 'paying'" class="rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm sm:p-8">
            <template v-if="paymentOutcome === 'successful'">
              <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
                <svg class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 class="mt-4 font-[Georgia] text-xl font-bold text-navy-900">Payment Received</h2>
              <p class="mt-2 text-sm text-slate-600">
                Booking #{{ booking?.id }} is confirmed. We've sent a confirmation to your email if you gave us one.
              </p>
              <RouterLink
                to="/account/bookings"
                class="mt-5 inline-block rounded-md bg-gold-500 px-5 py-2.5 text-sm font-semibold text-navy-950 transition hover:bg-gold-400"
              >
                View My Bookings
              </RouterLink>
            </template>

            <template v-else-if="paymentOutcome === 'failed'">
              <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-50 text-red-600">
                <svg class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h2 class="mt-4 font-[Georgia] text-xl font-bold text-navy-900">Payment Didn't Go Through</h2>
              <p class="mt-2 text-sm text-slate-600">
                The M-Pesa prompt was cancelled, timed out, or declined. No money has left your account - you can try
                again whenever you're ready.
              </p>
              <button
                class="mt-5 rounded-md bg-gold-500 px-5 py-2.5 text-sm font-semibold text-navy-950 transition hover:bg-gold-400"
                @click="retryPayment"
              >
                Try Again
              </button>
            </template>

            <template v-else-if="paymentOutcome === 'timeout'">
              <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-gold-500/10 text-gold-500">
                <svg class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
              </div>
              <h2 class="mt-4 font-[Georgia] text-xl font-bold text-navy-900">Still Waiting on M-Pesa</h2>
              <p class="mt-2 text-sm text-slate-600">
                This is taking longer than usual. If you already entered your PIN, check
                <RouterLink to="/account/bookings" class="font-semibold text-brand-blue-600 hover:underline">My Bookings</RouterLink>
                in a moment - it'll update once M-Pesa confirms. Otherwise, you can try again.
              </p>
              <button
                class="mt-5 rounded-md bg-gold-500 px-5 py-2.5 text-sm font-semibold text-navy-950 transition hover:bg-gold-400"
                @click="retryPayment"
              >
                Try Again
              </button>
            </template>

            <template v-else>
              <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-brand-blue-50 text-brand-blue-600">
                <svg class="h-7 w-7 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                </svg>
              </div>
              <h2 class="mt-4 font-[Georgia] text-xl font-bold text-navy-900">Check Your Phone</h2>
              <p class="mt-2 text-sm text-slate-600">
                We've sent an M-Pesa prompt to {{ paymentPhone }}. Enter your PIN to complete payment for
                booking #{{ booking?.id }}.
              </p>
            </template>
          </div>
        </div>

        <!-- Sidebar: live vehicle/cost summary (only once a vehicle is actually picked) -->
        <aside v-if="showSidebar" class="lg:col-span-1">
          <div
            class="rounded-2xl border border-slate-200 bg-white shadow-lg shadow-slate-200/60 lg:sticky lg:top-24"
          >
              <div
                class="group relative aspect-[4/3] w-full overflow-hidden rounded-t-2xl bg-slate-100"
                @mouseenter="stopPhotoTimer"
                @mouseleave="startPhotoTimer"
              >
                <Transition name="photo-fade">
                  <img
                    v-if="vehiclePhotos.length"
                    :key="photoIndex"
                    :src="vehiclePhotos[photoIndex].image"
                    :alt="vehiclePhotos[photoIndex].caption || selectedVehicle.name"
                    class="absolute inset-0 h-full w-full object-cover"
                  />
                </Transition>
                <div v-if="!vehiclePhotos.length" class="flex h-full items-center justify-center text-sm text-slate-400">No photo yet</div>

                <template v-if="vehiclePhotos.length > 1">
                  <button
                    type="button"
                    aria-label="Previous photo"
                    class="absolute left-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-navy-950/50 text-white opacity-0 transition group-hover:opacity-100 hover:bg-navy-950/80"
                    @click="prevPhoto"
                  >
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    aria-label="Next photo"
                    class="absolute right-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-navy-950/50 text-white opacity-0 transition group-hover:opacity-100 hover:bg-navy-950/80"
                    @click="nextPhoto"
                  >
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                  <div class="absolute bottom-2 left-1/2 flex -translate-x-1/2 gap-1.5">
                    <button
                      v-for="(photo, i) in vehiclePhotos"
                      :key="photo.id ?? i"
                      type="button"
                      :aria-label="`Show photo ${i + 1}`"
                      class="h-1.5 w-1.5 rounded-full transition"
                      :class="i === photoIndex ? 'bg-white' : 'bg-white/50'"
                      @click="goToPhoto(i)"
                    />
                  </div>
                </template>
              </div>
              <div class="p-5">
                <h3 class="font-[Georgia] text-lg font-bold uppercase tracking-wide text-navy-900">
                  {{ selectedVehicle.name }}
                </h3>
                <p class="text-sm font-semibold text-brand-blue-600">
                  {{ selectedVehicle.category_name || selectedVehicle.category }}
                </p>
                <p class="mt-1 text-sm text-slate-600">{{ selectedVehicle.passenger_capacity }} Passengers</p>
                <p class="mt-1 text-sm text-slate-500">
                  {{ form.service_type === 'with_driver' ? 'With Driver' : 'Self Drive' }}
                </p>

                <div class="mt-4 space-y-2 border-t border-slate-200 pt-4 text-sm">
                  <div class="flex justify-between text-slate-600">
                    <span>Rate</span>
                    <span>KES {{ Number(selectedVehicle.price_per_day).toLocaleString() }}/day</span>
                  </div>
                  <div v-if="totalDays" class="flex justify-between text-slate-600">
                    <span>{{ totalDays }} day{{ totalDays > 1 ? 's' : '' }}</span>
                    <span>&times; KES {{ Number(selectedVehicle.price_per_day).toLocaleString() }}</span>
                  </div>
                  <div v-if="totalDays && form.service_type === 'self_drive'" class="flex justify-between text-slate-600">
                    <span>Self-drive surcharge (3%)</span>
                    <span>+ KES {{ (totalCost - baseCost).toLocaleString() }}</span>
                  </div>
                  <div v-if="totalDays" class="flex justify-between border-t border-slate-200 pt-2 text-base font-bold text-navy-900">
                    <span>Total</span>
                    <span class="text-gold-500">KES {{ totalCost.toLocaleString() }}</span>
                  </div>
                  <p v-if="!totalDays" class="text-xs text-slate-500">Pick your dates to see the total cost.</p>
                </div>

                <div v-if="totalDays" class="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-500">
                  A 30% deposit (KES {{ Math.round(totalCost * 0.3).toLocaleString() }}) secures your booking - pay the
                  rest anytime before pickup.
                </div>

                <div class="mt-4 border-t border-slate-200 pt-4">
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
                    Discount Code (optional)
                  </label>
                  <input
                    v-model="form.discount_code" type="text" placeholder="e.g. WELCOME500"
                    class="w-full rounded-md border border-slate-200 px-3 py-2 text-sm uppercase text-slate-800 placeholder-slate-400 placeholder:normal-case focus:border-brand-blue-600 focus:outline-none"
                  />
                  <p class="mt-1 text-xs text-slate-400">Applied automatically when you book - it'll show on your total below.</p>
                </div>
              </div>
          </div>

          <AvailabilityCalendar :vehicle-id="selectedVehicle.id" class="mt-4" />
        </aside>
      </div>
    </div>
  </div>
</template>

<style scoped>
.photo-fade-enter-active,
.photo-fade-leave-active {
  transition: opacity 0.6s ease;
}
.photo-fade-enter-from,
.photo-fade-leave-to {
  opacity: 0;
}
</style>
