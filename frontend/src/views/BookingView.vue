<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import apiClient from '../api/client'
import AddressAutocomplete from '../components/AddressAutocomplete.vue'
import AvailabilityCalendar from '../components/AvailabilityCalendar.vue'
import PhoneInput from '../components/PhoneInput.vue'
import VehiclePhotoPlaceholder from '../components/VehiclePhotoPlaceholder.vue'
import { useAuthStore } from '../stores/auth'
import { useCatalogStore } from '../stores/catalog'
import { trackEvent } from '../utils/analytics'
import { calculateEstimatedCost, calculateTotalDays, SELF_DRIVE_SURCHARGE_PERCENT } from '../utils/pricing'

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
  pickup_lat: null,
  pickup_lng: null,
  dropoff_location: route.query.dropoff || '',
  dropoff_lat: null,
  dropoff_lng: null,
  start_date: route.query.start_date || '',
  end_date: route.query.end_date || '',
  notes: '',
  customer_license_number: '',
  discount_code: '',
  protection_plan: '',
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

// Temporary, easily-reversible: flip back to true once real M-Pesa production credentials are
// in place. Nothing about the M-Pesa flow itself (STK push, callback, polling) is removed -
// it's just not offered as a customer-facing option while this is false, in favor of Bank
// Transfer. Card was already a UI-only stub (see submitCardPayment) regardless of this flag.
const MPESA_ENABLED = false
const primaryMethod = computed(() => (MPESA_ENABLED ? 'mpesa' : 'bank_transfer'))

const paymentMethod = ref(primaryMethod.value) // 'mpesa' | 'bank_transfer' | 'card'
const payOption = ref('deposit') // 'deposit' | 'full'
const step = ref('form') // form -> confirmed -> paying
const booking = ref(null)
const submitting = ref(false)
const error = ref('')

const bankTransferAcknowledged = ref(false)
const bankTransferReference = ref('')
const declaringBankTransfer = ref(false)
const bankTransferError = ref('')
// A bank transfer the customer already declared on this booking, awaiting staff confirmation -
// shown instead of the payment options once present, same shape as the no-login pay page's own
// pendingOfflinePayment (see PayBookingView.vue).
const pendingBankTransferPayment = computed(() => {
  if (!booking.value) return null
  return (booking.value.pending_payments || []).find((p) => p.method === 'bank_transfer') || null
})
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
  } catch {
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
  catalog.fetchProtectionPlans()
  trackEvent('begin_checkout', {
    currency: 'KES',
    items: form.vehicle ? [{ item_id: String(form.vehicle) }] : [],
    service_type: form.service_type,
  })
})

// Only offer vehicles that actually support the chosen service type.
const availableVehicles = computed(() =>
  catalog.vehicles.filter((v) => (form.service_type === 'with_driver' ? v.allow_with_driver : v.allow_self_drive)),
)

// If the current service type no longer supports the selected vehicle, clear it. A protection
// plan only ever applies to self-drive (see Booking.clean()) - a stale selection shouldn't
// silently survive switching away from it.
watch(
  () => form.service_type,
  () => {
    if (form.vehicle && !availableVehicles.value.some((v) => v.id === form.vehicle)) {
      form.vehicle = ''
    }
    if (form.service_type !== 'self_drive') {
      form.protection_plan = ''
    }
  },
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
    } catch {
      // Advisory only - if this fails, the form still works, submit just won't warn early.
    }
  },
  { immediate: true },
)

const dateConflictWarning = computed(() => {
  if (!form.start_date || !form.end_date) return ''
  const conflict = bookedRanges.value.some(
    (range) => form.start_date <= range.end_date && form.end_date >= range.start_date,
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
  } catch {
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

const totalDays = computed(() => calculateTotalDays(form.start_date, form.end_date))

// Straight-line (great-circle) distance, not a driving route - the app doesn't price by
// distance, this is just so the customer can sanity-check how far apart the two points are.
const EARTH_RADIUS_KM = 6371
function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = (deg) => (deg * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

const pickupDropoffDistanceKm = computed(() => {
  if (form.pickup_lat == null || form.pickup_lng == null || form.dropoff_lat == null || form.dropoff_lng == null) {
    return null
  }
  return haversineKm(Number(form.pickup_lat), Number(form.pickup_lng), Number(form.dropoff_lat), Number(form.dropoff_lng))
})

const baseCost = computed(() => {
  if (!selectedVehicle.value) return 0
  return totalDays.value * Number(selectedVehicle.value.price_per_day)
})

const surchargedCost = computed(() => {
  if (!selectedVehicle.value) return 0
  return calculateEstimatedCost(selectedVehicle.value.price_per_day, totalDays.value, form.service_type)
})

// Self-drive only (see Booking.clean()) - priced per day like the vehicle's own rate, mirrors
// Booking.save()'s protection_plan_amount calculation.
const selectedProtectionPlan = computed(() =>
  catalog.protectionPlans.find((p) => p.id === Number(form.protection_plan)) || null,
)
const protectionPlanCost = computed(() => {
  if (form.service_type !== 'self_drive' || !selectedProtectionPlan.value) return 0
  return totalDays.value * Number(selectedProtectionPlan.value.price_per_day)
})

const totalCost = computed(() => surchargedCost.value + protectionPlanCost.value)

const amountToPay = computed(() => {
  if (!booking.value) return 0
  return payOption.value === 'full' ? Number(booking.value.balance_due) : Number(booking.value.deposit_amount)
})

async function submitBooking() {
  submitting.value = true
  error.value = ''
  try {
    const payload = new FormData()
    const coordFields = ['pickup_lat', 'pickup_lng', 'dropoff_lat', 'dropoff_lng']
    Object.entries(form).forEach(([key, value]) => {
      if (key === 'protection_plan' && !value) return
      // FormData.append(key, null) serializes to the literal string "null", which the backend's
      // DecimalField(allow_null=True) would then reject as an invalid decimal - skip entirely
      // when the customer never selected an autocomplete suggestion (the common free-text case).
      if (coordFields.includes(key) && !value) return
      payload.append(key, value)
    })
    if (form.service_type === 'self_drive') {
      payload.append('customer_license_document', licenseDocument.value)
      payload.append('customer_id_document', idDocument.value)
    }

    const { data } = await apiClient.post('/bookings/', payload)
    booking.value = data
    step.value = 'confirmed'
    refreshReferralCreditBalance()
    trackEvent('generate_lead', {
      currency: 'KES',
      value: Number(data.total_amount),
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
          transaction_id: String(booking.value.id),
          currency: 'KES',
          value: amountToPay.value,
          items: [{ item_id: String(booking.value.vehicle), item_name: selectedVehicle.value?.name }],
        })
      } else if (data.status === 'failed') {
        stopPolling()
        paymentOutcome.value = 'failed'
      } else if (pollAttempts >= MAX_POLL_ATTEMPTS) {
        stopPolling()
        paymentOutcome.value = 'timeout'
      }
    } catch {
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
  trackEvent('add_payment_info', { payment_type: 'mpesa', currency: 'KES', value: amountToPay.value })
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
    error.value =
      err.response?.data?.detail ||
      'Could not start M-Pesa payment. You can also pay via Paybill 400400 (Acc: SILVERLAKE).'
  } finally {
    submitting.value = false
  }
}

function retryPayment() {
  paymentOutcome.value = null
  step.value = 'confirmed'
}

async function declareBankTransfer() {
  trackEvent('add_payment_info', { payment_type: 'bank_transfer', currency: 'KES', value: amountToPay.value })
  declaringBankTransfer.value = true
  bankTransferError.value = ''
  try {
    await apiClient.post('/payments/bank-transfer/declare/', {
      booking: booking.value.id,
      amount: amountToPay.value,
      reference: bankTransferReference.value,
    })
    const { data } = await apiClient.get(`/bookings/${booking.value.id}/`)
    booking.value = data
    bankTransferAcknowledged.value = false
    bankTransferReference.value = ''
  } catch (err) {
    const data = err.response?.data
    bankTransferError.value =
      data?.detail || data?.reference?.[0] || 'Could not record your bank transfer. Please try again.'
  } finally {
    declaringBankTransfer.value = false
  }
}
</script>

<template>
  <div class="bg-page">
    <div class="mx-auto max-w-5xl px-4 py-12 sm:px-6 sm:py-16">
      <div class="text-center">
        <h1 class="font-[Georgia] text-3xl font-bold text-foreground sm:text-4xl">Book Your Ride</h1>
        <p class="mt-2 text-foreground-muted">Choose your vehicle, dates, and how you'd like to travel.</p>
      </div>

      <div class="mt-10 grid gap-8" :class="showSidebar ? 'lg:grid-cols-3' : 'mx-auto max-w-2xl'">
        <!-- Main column: form / confirmation / payment -->
        <div :class="showSidebar ? 'lg:col-span-2' : ''">
          <form
            v-if="step === 'form'"
            class="space-y-5 rounded-2xl border border-border-subtle bg-surface p-6 sm:p-8"
            @submit.prevent="submitBooking"
          >
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Service type</label>
              <div class="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  class="rounded-md border px-3 py-2 text-sm font-semibold transition"
                  :class="
                    form.service_type === 'with_driver'
                      ? 'border-accent-border-strong bg-accent-bg text-on-accent'
                      : 'border-border text-foreground-secondary'
                  "
                  @click="form.service_type = 'with_driver'"
                >
                  Book with Driver
                </button>
                <button
                  type="button"
                  class="rounded-md border px-3 py-2 text-sm font-semibold transition"
                  :class="
                    form.service_type === 'self_drive'
                      ? 'border-accent-border-strong bg-accent-bg text-on-accent'
                      : 'border-border text-foreground-secondary'
                  "
                  @click="form.service_type = 'self_drive'"
                >
                  Self Drive
                </button>
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Vehicle</label>
              <select
                v-model.number="form.vehicle"
                required
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              >
                <option value="" disabled>Select a vehicle</option>
                <option v-for="v in availableVehicles" :key="v.id" :value="v.id">
                  {{ v.name }} - KES {{ Number(v.price_per_day).toLocaleString() }}/day
                </option>
              </select>
              <p v-if="!availableVehicles.length" class="mt-1 text-xs text-foreground-subtle">
                No vehicles currently support this service type.
              </p>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="mb-1 block text-sm text-foreground-muted">Start date</label>
                <input
                  v-model="form.start_date"
                  type="date"
                  :min="today"
                  required
                  class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground [color-scheme:dark] focus:border-accent-border focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm text-foreground-muted">End date</label>
                <input
                  v-model="form.end_date"
                  type="date"
                  :min="form.start_date || today"
                  required
                  class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground [color-scheme:dark] focus:border-accent-border focus:outline-none"
                />
              </div>
            </div>

            <div
              v-if="dateConflictWarning"
              class="rounded-lg border border-accent-border-strong/40 bg-accent-bg/10 px-3 py-2.5 text-sm text-foreground"
            >
              <p class="flex items-start gap-2">
                <svg
                  class="mt-0.5 h-4 w-4 shrink-0 text-accent-strong"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    d="M12 9v3.75m0 3.75h.008M10.29 3.86L1.82 18a1.5 1.5 0 001.29 2.25h17.78a1.5 1.5 0 001.29-2.25L13.71 3.86a1.5 1.5 0 00-2.42 0z"
                  />
                </svg>
                <span>{{ dateConflictWarning }}</span>
              </p>

              <div class="mt-2 pl-6">
                <p v-if="onWaitlistFor" class="text-accent">
                  You're on the waitlist for these dates - we'll email you if it opens up.
                  <button
                    type="button"
                    :disabled="joiningWaitlist"
                    class="ml-1 font-semibold underline disabled:opacity-60"
                    @click="leaveWaitlist"
                  >
                    Leave waitlist
                  </button>
                </p>
                <button
                  v-else
                  type="button"
                  :disabled="joiningWaitlist"
                  class="rounded-md border border-border px-3 py-1.5 text-sm font-semibold text-foreground transition hover:bg-surface-2 disabled:opacity-60"
                  @click="joinWaitlist"
                >
                  {{ joiningWaitlist ? 'Joining...' : 'Notify me if it opens up' }}
                </button>
                <p v-if="waitlistError" class="mt-1 text-danger">{{ waitlistError }}</p>
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Pickup location</label>
              <AddressAutocomplete
                v-model="form.pickup_location"
                required
                @select="(coords) => { form.pickup_lat = coords?.lat ?? null; form.pickup_lng = coords?.lng ?? null }"
              />
              <p class="mt-1 text-xs text-foreground-subtle">
                Start typing and pick a suggestion so your driver gets your exact location.
              </p>
            </div>

            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Drop-off location (optional)</label>
              <AddressAutocomplete
                v-model="form.dropoff_location"
                @select="(coords) => { form.dropoff_lat = coords?.lat ?? null; form.dropoff_lng = coords?.lng ?? null }"
              />
              <p v-if="pickupDropoffDistanceKm !== null" class="mt-1 text-xs text-foreground-subtle">
                Straight-line distance: {{ pickupDropoffDistanceKm.toFixed(1) }} km
              </p>
            </div>

            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Who is this trip for?</label>
              <div class="inline-flex rounded-lg border border-border bg-surface-2 p-1">
                <button
                  type="button"
                  class="rounded-md px-4 py-1.5 text-sm font-semibold transition"
                  :class="
                    bookingFor === 'myself' ? 'bg-page text-foreground shadow-sm' : 'text-foreground-subtle hover:text-foreground'
                  "
                  @click="bookingFor = 'myself'"
                >
                  Myself
                </button>
                <button
                  type="button"
                  class="rounded-md px-4 py-1.5 text-sm font-semibold transition"
                  :class="
                    bookingFor === 'someone_else'
                      ? 'bg-page text-foreground shadow-sm'
                      : 'text-foreground-subtle hover:text-foreground'
                  "
                  @click="bookingFor = 'someone_else'"
                >
                  Someone else
                </button>
              </div>
              <p v-if="bookingFor === 'someone_else'" class="mt-1.5 text-xs text-foreground-subtle">
                Enter the rider's details below - the M-Pesa payment step further down still charges your own number.
              </p>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="mb-1 block text-sm text-foreground-muted">{{
                  bookingFor === 'someone_else' ? "Rider's name" : 'Your name'
                }}</label>
                <input
                  v-model="form.customer_name"
                  type="text"
                  required
                  class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm text-foreground-muted">{{
                  bookingFor === 'someone_else' ? "Rider's phone" : 'Your phone'
                }}</label>
                <PhoneInput v-model="form.customer_phone" required />
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm text-foreground-muted">
                {{ bookingFor === 'someone_else' ? "Rider's email (optional)" : 'Email (optional)' }}
              </label>
              <input
                v-model="form.customer_email"
                type="email"
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              />
            </div>

            <div
              v-if="form.service_type === 'self_drive'"
              class="space-y-4 rounded-md border border-accent-border/40 bg-accent-bg/5 p-4"
            >
              <p class="text-sm font-semibold text-accent">
                Self-drive requires proof of a valid license and ID before we hand over the vehicle.
              </p>
              <div>
                <label class="mb-1 block text-sm text-foreground-muted">Driving license number</label>
                <input
                  v-model="form.customer_license_number"
                  type="text"
                  required
                  class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm text-foreground-muted">Driving license document (photo or PDF)</label>
                <input
                  type="file"
                  required
                  accept="image/*,.pdf"
                  class="w-full text-sm text-foreground-muted file:mr-3 file:rounded-md file:border-0 file:bg-accent-bg file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-on-accent"
                  @change="licenseDocument = $event.target.files[0]"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm text-foreground-muted">National ID or passport copy</label>
                <input
                  type="file"
                  required
                  accept="image/*,.pdf"
                  class="w-full text-sm text-foreground-muted file:mr-3 file:rounded-md file:border-0 file:bg-accent-bg file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-on-accent"
                  @change="idDocument = $event.target.files[0]"
                />
              </div>
            </div>

            <div v-if="form.service_type === 'self_drive' && catalog.protectionPlans.length">
              <label class="mb-1 block text-sm text-foreground-muted">Protection plan (optional)</label>
              <div class="space-y-2">
                <button
                  type="button"
                  class="w-full rounded-md border px-3 py-2 text-left text-sm transition"
                  :class="
                    !form.protection_plan
                      ? 'border-accent-border bg-accent-bg/10'
                      : 'border-border hover:border-accent-border/50'
                  "
                  @click="form.protection_plan = ''"
                >
                  <span class="font-semibold text-foreground">No protection plan</span>
                </button>
                <button
                  v-for="plan in catalog.protectionPlans"
                  :key="plan.id"
                  type="button"
                  class="w-full rounded-md border px-3 py-2 text-left text-sm transition"
                  :class="
                    Number(form.protection_plan) === plan.id
                      ? 'border-accent-border bg-accent-bg/10'
                      : 'border-border hover:border-accent-border/50'
                  "
                  @click="form.protection_plan = plan.id"
                >
                  <span class="flex items-center justify-between">
                    <span class="font-semibold text-foreground">{{ plan.name }}</span>
                    <span class="text-foreground-subtle">KES {{ Number(plan.price_per_day).toLocaleString() }}/day</span>
                  </span>
                  <span v-if="plan.excess_reduction_description" class="mt-0.5 block text-xs text-foreground-subtle">
                    {{ plan.excess_reduction_description }}
                  </span>
                </button>
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Discount Code (optional)</label>
              <input
                v-model="form.discount_code"
                type="text"
                placeholder="e.g. WELCOME500"
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-sm uppercase text-foreground placeholder-foreground-subtle placeholder:normal-case focus:border-accent-border focus:outline-none"
              />
              <p class="mt-1 text-xs text-foreground-subtle">
                Applied automatically when you book - it'll show on your total below.
              </p>
            </div>

            <p v-if="error" class="text-sm text-danger">{{ error }}</p>

            <button
              type="submit"
              :disabled="submitting"
              class="w-full rounded-md bg-accent-bg px-4 py-2.5 font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
            >
              {{ submitting ? 'Submitting...' : 'Confirm Booking' }}
            </button>
          </form>

          <div v-else-if="step === 'confirmed'" class="rounded-2xl border border-border-subtle bg-surface shadow-sm">
            <!-- Success header -->
            <div class="flex items-start gap-4 border-b border-border-subtle p-6 sm:p-8">
              <div
                class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-500/10 text-success"
              >
                <svg class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div>
                <h2 class="font-[Georgia] text-xl font-bold text-foreground">Booking Received</h2>
                <p class="mt-1 text-sm text-foreground-subtle">
                  Reference <span class="font-mono text-foreground-secondary">#{{ booking?.id }}</span>
                </p>
              </div>
            </div>

            <!-- Receipt summary -->
            <div class="border-b border-border-subtle px-6 py-4 text-sm sm:px-8">
              <div class="flex items-center justify-between py-1.5">
                <span class="text-foreground-subtle">Vehicle</span>
                <span class="font-medium text-foreground">{{ selectedVehicle?.name }}</span>
              </div>
              <div
                v-if="Number(booking.discount_amount) > 0"
                class="flex items-center justify-between py-1.5 text-success"
              >
                <span>Discount ({{ booking.discount_code_display }})</span>
                <span class="font-medium">- KES {{ Number(booking.discount_amount).toLocaleString() }}</span>
              </div>
              <div
                v-if="Number(booking.loyalty_discount_amount) > 0"
                class="flex items-center justify-between py-1.5 text-success"
              >
                <span>Loyalty Discount</span>
                <span class="font-medium">- KES {{ Number(booking.loyalty_discount_amount).toLocaleString() }}</span>
              </div>
              <div
                v-if="Number(booking.protection_plan_amount) > 0"
                class="flex items-center justify-between py-1.5"
              >
                <span class="text-foreground-subtle">{{ booking.protection_plan_name }} protection</span>
                <span class="font-medium text-foreground">
                  + KES {{ Number(booking.protection_plan_amount).toLocaleString() }}
                </span>
              </div>
              <div class="flex items-center justify-between border-t border-dashed border-border-subtle py-1.5 pt-2.5">
                <span class="font-semibold text-foreground">Trip Total</span>
                <span class="font-[Georgia] text-lg font-bold text-foreground">
                  KES {{ Number(booking.total_amount).toLocaleString() }}
                </span>
              </div>
            </div>

            <div v-if="pendingBankTransferPayment" class="p-6 text-center sm:p-8">
              <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-accent-bg/10 text-accent-strong">
                <svg class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    d="M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
                  />
                </svg>
              </div>
              <h2 class="mt-4 font-[Georgia] text-lg font-bold text-foreground">Awaiting Confirmation</h2>
              <p class="mt-2 text-sm text-foreground-muted">
                You've declared a bank transfer of KES {{ Number(pendingBankTransferPayment.amount).toLocaleString() }}
                <span v-if="pendingBankTransferPayment.note">(ref. {{ pendingBankTransferPayment.note }})</span>. Once
                our team confirms it's been received, your balance will be updated.
              </p>
            </div>

            <div v-else class="p-6 sm:p-8">
              <label class="mb-2 block text-sm font-semibold text-foreground">How much would you like to pay now?</label>
              <div class="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  class="rounded-xl border-2 p-3 text-left transition"
                  :class="
                    payOption === 'deposit'
                      ? 'border-accent-border bg-accent-bg/10'
                      : 'border-border hover:border-accent-border/50'
                  "
                  @click="payOption = 'deposit'"
                >
                  <span class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-foreground-subtle">
                    <span
                      class="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border-2"
                      :class="payOption === 'deposit' ? 'border-accent-border' : 'border-border'"
                    >
                      <span v-if="payOption === 'deposit'" class="h-1.5 w-1.5 rounded-full bg-accent-bg-hover" />
                    </span>
                    Deposit (30%)
                  </span>
                  <span class="mt-1 block font-[Georgia] text-lg font-bold text-foreground">
                    KES {{ Number(booking.deposit_amount).toLocaleString() }}
                  </span>
                </button>
                <button
                  type="button"
                  class="rounded-xl border-2 p-3 text-left transition"
                  :class="
                    payOption === 'full'
                      ? 'border-accent-border bg-accent-bg/10'
                      : 'border-border hover:border-accent-border/50'
                  "
                  @click="payOption = 'full'"
                >
                  <span class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-foreground-subtle">
                    <span
                      class="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border-2"
                      :class="payOption === 'full' ? 'border-accent-border' : 'border-border'"
                    >
                      <span v-if="payOption === 'full'" class="h-1.5 w-1.5 rounded-full bg-accent-bg-hover" />
                    </span>
                    Pay in Full
                  </span>
                  <span class="mt-1 block font-[Georgia] text-lg font-bold text-foreground">
                    KES {{ Number(booking.balance_due).toLocaleString() }}
                  </span>
                </button>
              </div>

              <div
                v-if="referralCreditBalance > 0 && booking.balance_due > 0"
                class="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-accent-border-strong/40 bg-accent-bg/10 p-4"
              >
                <p class="text-sm text-foreground">
                  You have <span class="font-bold">KES {{ Number(referralCreditBalance).toLocaleString() }}</span> in
                  referral credit available.
                </p>
                <button
                  type="button"
                  :disabled="applyingCredit"
                  class="shrink-0 rounded-md bg-accent-bg px-4 py-2 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
                  @click="applyReferralCredit"
                >
                  {{ applyingCredit ? 'Applying...' : 'Apply Credit' }}
                </button>
              </div>
              <p v-if="creditError" class="mt-2 text-sm text-danger">{{ creditError }}</p>

              <label class="mb-2 mt-5 block text-sm font-semibold text-foreground">Payment method</label>
              <div class="inline-flex rounded-lg border border-border bg-surface-2 p-1">
                <button
                  class="rounded-md px-4 py-1.5 text-sm font-semibold transition"
                  :class="
                    paymentMethod === primaryMethod
                      ? 'bg-page text-foreground shadow-sm'
                      : 'text-foreground-subtle hover:text-foreground'
                  "
                  @click="paymentMethod = primaryMethod"
                >
                  {{ MPESA_ENABLED ? 'M-Pesa' : 'Bank Transfer' }}
                </button>
                <button
                  class="rounded-md px-4 py-1.5 text-sm font-semibold transition"
                  :class="
                    paymentMethod === 'card' ? 'bg-page text-foreground shadow-sm' : 'text-foreground-subtle hover:text-foreground'
                  "
                  @click="paymentMethod = 'card'"
                >
                  Card
                </button>
              </div>

              <div v-if="paymentMethod === 'mpesa'" class="mt-5">
                <label class="mb-1 block text-sm text-foreground-muted">M-Pesa number to charge</label>
                <PhoneInput v-model="paymentPhone" required />
                <p class="mt-1 text-xs text-foreground-subtle">
                  This is charged to you, the account holder - it doesn't need to match the rider's own phone above.
                </p>

                <p
                  v-if="error"
                  class="mb-3 mt-3 flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2.5 text-sm text-danger"
                >
                  <svg
                    class="mt-0.5 h-4 w-4 shrink-0"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M12 9v3.75m0 3.75h.008M10.29 3.86L1.82 18a1.5 1.5 0 001.29 2.25h17.78a1.5 1.5 0 001.29-2.25L13.71 3.86a1.5 1.5 0 00-2.42 0z"
                    />
                  </svg>
                  <span>{{ error }}</span>
                </p>
                <button
                  :disabled="submitting"
                  class="mt-3 w-full rounded-md bg-accent-bg px-4 py-2.5 font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
                  @click="payWithMpesa"
                >
                  {{ submitting ? 'Sending prompt...' : `Pay KES ${amountToPay.toLocaleString()} via M-Pesa` }}
                </button>
              </div>

              <div v-else-if="paymentMethod === 'bank_transfer'" class="mt-5 space-y-3">
                <div class="rounded-md border border-border bg-surface-2 p-4 text-sm text-foreground-secondary">
                  <p class="font-semibold text-foreground">Pay via Bank Transfer</p>
                  <p class="mt-2">Co-operative Bank of Kenya</p>
                  <p>Paybill <span class="font-semibold text-foreground">400200</span></p>
                  <p>Account No: <span class="font-semibold text-foreground">01101465587001</span></p>
                  <p class="mt-2 text-xs text-foreground-subtle">
                    Use your name and booking #{{ booking?.id }} as the transfer reference, so we can match your
                    payment.
                  </p>
                </div>

                <div>
                  <label class="mb-1 block text-sm text-foreground-muted">Transaction reference</label>
                  <input
                    v-model="bankTransferReference"
                    type="text"
                    placeholder="e.g. last 4 digits of the M-Pesa/bank code"
                    class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-foreground focus:border-accent-border focus:outline-none"
                  />
                  <p class="mt-1 text-xs text-foreground-subtle">
                    Check the confirmation SMS from your bank/M-Pesa - at least the last 4 digits/characters are enough.
                  </p>
                </div>

                <div class="rounded-md border border-border bg-surface p-3 text-sm text-foreground-secondary">
                  <label class="flex items-start gap-2">
                    <input v-model="bankTransferAcknowledged" type="checkbox" class="mt-0.5" />
                    <span
                      >I confirm I have sent KES {{ amountToPay.toLocaleString() }} via bank transfer to the account
                      above.</span
                    >
                  </label>
                </div>

                <p v-if="bankTransferError" class="text-sm text-danger">{{ bankTransferError }}</p>

                <button
                  :disabled="
                    declaringBankTransfer || !bankTransferAcknowledged || bankTransferReference.trim().length < 4
                  "
                  class="w-full rounded-md bg-accent-bg px-4 py-2.5 font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
                  @click="declareBankTransfer"
                >
                  {{
                    declaringBankTransfer
                      ? 'Recording...'
                      : `I've Sent KES ${amountToPay.toLocaleString()} via Bank Transfer`
                  }}
                </button>
              </div>

              <form v-else class="mt-5 space-y-3" @submit.prevent="submitCardPayment">
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-subtle"
                    >Card Number</label
                  >
                  <input
                    :value="card.number"
                    type="text"
                    inputmode="numeric"
                    autocomplete="cc-number"
                    placeholder="1234 5678 9012 3456"
                    maxlength="19"
                    class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 font-mono tracking-wide text-foreground focus:border-accent-border focus:outline-none"
                    @input="onCardNumberInput"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-subtle"
                    >Cardholder Name</label
                  >
                  <input
                    v-model="card.name"
                    type="text"
                    autocomplete="cc-name"
                    placeholder="Jane Doe"
                    class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
                  />
                </div>
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-subtle">Expiry</label>
                    <input
                      :value="card.expiry"
                      type="text"
                      inputmode="numeric"
                      autocomplete="cc-exp"
                      placeholder="MM/YY"
                      maxlength="5"
                      class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-foreground focus:border-accent-border focus:outline-none"
                      @input="onCardExpiryInput"
                    />
                  </div>
                  <div>
                    <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-subtle">CVV</label>
                    <input
                      :value="card.cvv"
                      type="password"
                      inputmode="numeric"
                      autocomplete="cc-csc"
                      placeholder="123"
                      maxlength="4"
                      class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-foreground focus:border-accent-border focus:outline-none"
                      @input="onCardCvvInput"
                    />
                  </div>
                </div>

                <p
                  v-if="cardNotice"
                  class="flex items-start gap-2 rounded-lg border border-accent-border-strong/40 bg-accent-bg/10 px-3 py-2.5 text-sm text-foreground"
                >
                  <svg
                    class="mt-0.5 h-4 w-4 shrink-0 text-accent-strong"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  <span>{{ cardNotice }}</span>
                </p>

                <button
                  type="submit"
                  class="w-full rounded-md bg-accent-bg px-4 py-2.5 font-semibold text-on-accent transition hover:bg-accent-bg-hover"
                >
                  Pay KES {{ amountToPay.toLocaleString() }} by Card
                </button>
                <p class="text-center text-xs text-foreground-subtle">
                  Secured payment - your card details are never stored on our servers.
                </p>
              </form>
            </div>
          </div>

          <div
            v-else-if="step === 'paying'"
            class="rounded-2xl border border-border-subtle bg-surface p-6 text-center shadow-sm sm:p-8"
          >
            <template v-if="paymentOutcome === 'successful'">
              <div
                class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/10 text-success"
              >
                <svg class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 class="mt-4 font-[Georgia] text-xl font-bold text-foreground">Payment Received</h2>
              <p class="mt-2 text-sm text-foreground-muted">
                Booking #{{ booking?.id }} is confirmed. We've sent a confirmation to your email if you gave us one.
              </p>
              <RouterLink
                to="/account/bookings"
                class="mt-5 inline-block rounded-md bg-accent-bg px-5 py-2.5 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover"
              >
                View My Bookings
              </RouterLink>
            </template>

            <template v-else-if="paymentOutcome === 'failed'">
              <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-500/10 text-danger">
                <svg class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h2 class="mt-4 font-[Georgia] text-xl font-bold text-foreground">Payment Didn't Go Through</h2>
              <p class="mt-2 text-sm text-foreground-muted">
                The M-Pesa prompt was cancelled, timed out, or declined. No money has left your account - you can try
                again whenever you're ready.
              </p>
              <button
                class="mt-5 rounded-md bg-accent-bg px-5 py-2.5 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover"
                @click="retryPayment"
              >
                Try Again
              </button>
            </template>

            <template v-else-if="paymentOutcome === 'timeout'">
              <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-accent-bg/10 text-accent-strong">
                <svg class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    d="M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
                  />
                </svg>
              </div>
              <h2 class="mt-4 font-[Georgia] text-xl font-bold text-foreground">Still Waiting on M-Pesa</h2>
              <p class="mt-2 text-sm text-foreground-muted">
                This is taking longer than usual. If you already entered your PIN, check
                <RouterLink to="/account/bookings" class="font-semibold text-accent hover:underline"
                  >My Bookings</RouterLink
                >
                in a moment - it'll update once M-Pesa confirms. Otherwise, you can try again.
              </p>
              <button
                class="mt-5 rounded-md bg-accent-bg px-5 py-2.5 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover"
                @click="retryPayment"
              >
                Try Again
              </button>
            </template>

            <template v-else>
              <div
                class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-accent-bg/10 text-accent"
              >
                <svg class="h-7 w-7 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                </svg>
              </div>
              <h2 class="mt-4 font-[Georgia] text-xl font-bold text-foreground">Check Your Phone</h2>
              <p class="mt-2 text-sm text-foreground-muted">
                We've sent an M-Pesa prompt to {{ paymentPhone }}. Enter your PIN to complete payment for booking #{{
                  booking?.id
                }}.
              </p>
            </template>
          </div>
        </div>

        <!-- Sidebar: live vehicle/cost summary (only once a vehicle is actually picked) -->
        <aside v-if="showSidebar" class="lg:col-span-1">
          <div class="rounded-2xl border border-border-subtle bg-surface shadow-lg shadow-black/20 lg:sticky lg:top-24">
            <div
              class="group relative aspect-[4/3] w-full overflow-hidden rounded-t-2xl bg-surface-2"
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
              <VehiclePhotoPlaceholder v-if="!vehiclePhotos.length" />

              <template v-if="vehiclePhotos.length > 1">
                <button
                  type="button"
                  aria-label="Previous photo"
                  class="absolute left-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-page/50 text-foreground opacity-0 transition group-hover:opacity-100 hover:bg-page/80"
                  @click="prevPhoto"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
                  </svg>
                </button>
                <button
                  type="button"
                  aria-label="Next photo"
                  class="absolute right-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-page/50 text-foreground opacity-0 transition group-hover:opacity-100 hover:bg-page/80"
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
              <h3 class="font-[Georgia] text-lg font-bold uppercase tracking-wide text-foreground">
                {{ selectedVehicle.name }}
              </h3>
              <p class="text-sm font-semibold text-accent">
                {{ selectedVehicle.category_name || selectedVehicle.category }}
              </p>
              <p class="mt-1 text-sm text-foreground-muted">{{ selectedVehicle.passenger_capacity }} Passengers</p>
              <p class="mt-1 text-sm text-foreground-subtle">
                {{ form.service_type === 'with_driver' ? 'With Driver' : 'Self Drive' }}
              </p>

              <div class="mt-4 space-y-2 border-t border-border-subtle pt-4 text-sm">
                <div class="flex justify-between text-foreground-muted">
                  <span>Rate</span>
                  <span>KES {{ Number(selectedVehicle.price_per_day).toLocaleString() }}/day</span>
                </div>
                <div v-if="totalDays" class="flex justify-between text-foreground-muted">
                  <span>{{ totalDays }} day{{ totalDays > 1 ? 's' : '' }}</span>
                  <span>&times; KES {{ Number(selectedVehicle.price_per_day).toLocaleString() }}</span>
                </div>
                <div v-if="totalDays && form.service_type === 'self_drive'" class="flex justify-between text-foreground-muted">
                  <span>Self-drive surcharge ({{ SELF_DRIVE_SURCHARGE_PERCENT }}%)</span>
                  <span>+ KES {{ (surchargedCost - baseCost).toLocaleString() }}</span>
                </div>
                <div v-if="totalDays && protectionPlanCost" class="flex justify-between text-foreground-muted">
                  <span>{{ selectedProtectionPlan?.name }} protection</span>
                  <span>+ KES {{ protectionPlanCost.toLocaleString() }}</span>
                </div>
                <div
                  v-if="totalDays"
                  class="flex justify-between border-t border-border-subtle pt-2 text-base font-bold text-foreground"
                >
                  <span>Total</span>
                  <span class="text-accent-strong">KES {{ totalCost.toLocaleString() }}</span>
                </div>
                <p v-if="!totalDays" class="text-xs text-foreground-subtle">Pick your dates to see the total cost.</p>
              </div>

              <div v-if="totalDays" class="mt-3 rounded-md bg-surface-2 px-3 py-2 text-xs text-foreground-muted">
                A 30% deposit (KES {{ Math.round(totalCost * 0.3).toLocaleString() }}) secures your booking - pay the
                rest anytime before pickup.
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
