<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import apiClient from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useCatalogStore } from '../stores/catalog'

const route = useRoute()
const catalog = useCatalogStore()
const auth = useAuthStore()

const form = reactive({
  vehicle: route.query.vehicle ? Number(route.query.vehicle) : '',
  service_type: route.query.service || 'with_driver',
  customer_name: auth.user ? `${auth.user.first_name} ${auth.user.last_name}`.trim() : '',
  customer_phone: auth.user?.phone_number || '',
  customer_email: auth.user?.email || '',
  pickup_location: '',
  dropoff_location: '',
  start_date: '',
  end_date: '',
  notes: '',
  customer_license_number: '',
})

const licenseDocument = ref(null)
const idDocument = ref(null)

const paymentMethod = ref('mpesa')
const payOption = ref('deposit') // 'deposit' | 'full'
const step = ref('form') // form -> confirmed -> paying
const booking = ref(null)
const submitting = ref(false)
const error = ref('')
const today = new Date().toISOString().split('T')[0]

onMounted(() => {
  catalog.fetchVehicles()
})

const selectedVehicle = computed(() => catalog.vehicles.find((v) => v.id === form.vehicle))

const totalDays = computed(() => {
  if (!form.start_date || !form.end_date) return 0
  const diff = (new Date(form.end_date) - new Date(form.start_date)) / (1000 * 60 * 60 * 24)
  return Math.max(1, Math.round(diff) + 1)
})

const totalCost = computed(() => {
  if (!selectedVehicle.value) return 0
  return totalDays.value * Number(selectedVehicle.value.price_per_day)
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
  } catch (err) {
    error.value = err.response?.data?.non_field_errors?.[0] || 'Something went wrong. Please check the form and try again.'
  } finally {
    submitting.value = false
  }
}

async function payWithMpesa() {
  submitting.value = true
  error.value = ''
  try {
    await apiClient.post('/payments/mpesa/stk-push/', {
      booking: booking.value.id,
      phone_number: form.customer_phone,
      amount: amountToPay.value,
    })
    step.value = 'paying'
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not start M-Pesa payment. You can also pay via Paybill 400400 (Acc: SILVERLAKE).'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-2xl px-4 py-16 sm:px-6">
    <h1 class="text-center font-[Georgia] text-3xl font-bold text-white">Book Your Ride</h1>
    <p class="mt-2 text-center text-slate-400">Choose your vehicle, dates, and how you'd like to travel.</p>

    <form v-if="step === 'form'" class="mt-10 space-y-5 rounded-xl border border-navy-800 bg-navy-900 p-6" @submit.prevent="submitBooking">
      <div>
        <label class="mb-1 block text-sm text-slate-300">Vehicle</label>
        <select
          v-model.number="form.vehicle"
          required
          class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
        >
          <option value="" disabled>Select a vehicle</option>
          <option v-for="v in catalog.vehicles" :key="v.id" :value="v.id">
            {{ v.name }} - KES {{ Number(v.price_per_day).toLocaleString() }}/day
          </option>
        </select>
      </div>

      <div>
        <label class="mb-1 block text-sm text-slate-300">Service type</label>
        <div class="grid grid-cols-2 gap-3">
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm font-semibold transition"
            :class="form.service_type === 'with_driver' ? 'border-gold-500 bg-gold-500 text-navy-950' : 'border-navy-700 text-slate-300'"
            @click="form.service_type = 'with_driver'"
          >
            Book with Driver
          </button>
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm font-semibold transition"
            :class="form.service_type === 'self_drive' ? 'border-gold-500 bg-gold-500 text-navy-950' : 'border-navy-700 text-slate-300'"
            @click="form.service_type = 'self_drive'"
          >
            Self Drive
          </button>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="mb-1 block text-sm text-slate-300">Start date</label>
          <input
            v-model="form.start_date"
            type="date"
            :min="today"
            required
            class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm text-slate-300">End date</label>
          <input
            v-model="form.end_date"
            type="date"
            :min="form.start_date || today"
            required
            class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
          />
        </div>
      </div>

      <div>
        <label class="mb-1 block text-sm text-slate-300">Pickup location</label>
        <input
          v-model="form.pickup_location"
          type="text"
          required
          class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
        />
      </div>

      <div>
        <label class="mb-1 block text-sm text-slate-300">Drop-off location (optional)</label>
        <input
          v-model="form.dropoff_location"
          type="text"
          class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
        />
      </div>

      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="mb-1 block text-sm text-slate-300">Your name</label>
          <input
            v-model="form.customer_name"
            type="text"
            required
            class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm text-slate-300">Phone (M-Pesa)</label>
          <input
            v-model="form.customer_phone"
            type="tel"
            placeholder="2547XXXXXXXX"
            required
            class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
          />
        </div>
      </div>

      <div>
        <label class="mb-1 block text-sm text-slate-300">Email (optional)</label>
        <input
          v-model="form.customer_email"
          type="email"
          class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
        />
      </div>

      <div v-if="form.service_type === 'self_drive'" class="space-y-4 rounded-md border border-navy-700 p-4">
        <p class="text-sm font-semibold text-gold-400">
          Self-drive requires proof of a valid license and ID before we hand over the vehicle.
        </p>
        <div>
          <label class="mb-1 block text-sm text-slate-300">Driving license number</label>
          <input
            v-model="form.customer_license_number"
            type="text"
            required
            class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm text-slate-300">Driving license document (photo or PDF)</label>
          <input
            type="file"
            required
            accept="image/*,.pdf"
            class="w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
            @change="licenseDocument = $event.target.files[0]"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm text-slate-300">National ID or passport copy</label>
          <input
            type="file"
            required
            accept="image/*,.pdf"
            class="w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
            @change="idDocument = $event.target.files[0]"
          />
        </div>
      </div>

      <div v-if="totalDays" class="rounded-md bg-navy-800 px-4 py-3 text-sm text-slate-200">
        {{ totalDays }} day{{ totalDays > 1 ? 's' : '' }} &times; KES {{ selectedVehicle ? Number(selectedVehicle.price_per_day).toLocaleString() : 0 }}
        = <span class="font-bold text-gold-400">KES {{ totalCost.toLocaleString() }}</span>
      </div>

      <p v-if="error" class="text-sm text-red-400">{{ error }}</p>

      <button
        type="submit"
        :disabled="submitting"
        class="w-full rounded-md bg-gold-500 px-4 py-2 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
      >
        {{ submitting ? 'Submitting...' : 'Confirm Booking' }}
      </button>
    </form>

    <div v-else-if="step === 'confirmed'" class="mt-10 rounded-xl border border-navy-800 bg-navy-900 p-6">
      <h2 class="font-[Georgia] text-xl font-bold text-gold-400">Booking received!</h2>
      <p class="mt-2 text-sm text-slate-300">
        We've logged your booking for {{ selectedVehicle?.name }} - total KES
        {{ Number(booking.total_amount).toLocaleString() }}.
      </p>

      <div class="mt-4">
        <label class="mb-1 block text-sm text-slate-300">How much would you like to pay now?</label>
        <div class="grid grid-cols-2 gap-3">
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm font-semibold"
            :class="payOption === 'deposit' ? 'border-gold-500 bg-gold-500 text-navy-950' : 'border-navy-700 text-slate-300'"
            @click="payOption = 'deposit'"
          >
            Deposit (30%)<br />
            <span class="text-xs font-normal">KES {{ Number(booking.deposit_amount).toLocaleString() }}</span>
          </button>
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm font-semibold"
            :class="payOption === 'full' ? 'border-gold-500 bg-gold-500 text-navy-950' : 'border-navy-700 text-slate-300'"
            @click="payOption = 'full'"
          >
            Pay in Full<br />
            <span class="text-xs font-normal">KES {{ Number(booking.balance_due).toLocaleString() }}</span>
          </button>
        </div>
      </div>

      <div class="mt-4 flex gap-3">
        <button
          class="rounded-md border px-3 py-2 text-sm font-semibold"
          :class="paymentMethod === 'mpesa' ? 'border-gold-500 bg-gold-500 text-navy-950' : 'border-navy-700 text-slate-300'"
          @click="paymentMethod = 'mpesa'"
        >
          M-Pesa
        </button>
        <button
          class="rounded-md border px-3 py-2 text-sm font-semibold"
          :class="paymentMethod === 'card' ? 'border-gold-500 bg-gold-500 text-navy-950' : 'border-navy-700 text-slate-300'"
          @click="paymentMethod = 'card'"
        >
          Card
        </button>
      </div>

      <div v-if="paymentMethod === 'mpesa'" class="mt-4">
        <p v-if="error" class="mb-2 text-sm text-red-400">{{ error }}</p>
        <button
          :disabled="submitting"
          class="w-full rounded-md bg-gold-500 px-4 py-2 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
          @click="payWithMpesa"
        >
          {{ submitting ? 'Sending prompt...' : `Pay KES ${amountToPay.toLocaleString()} via M-Pesa` }}
        </button>
      </div>

      <div v-else class="mt-4 text-sm text-slate-300">
        Card payments are being set up. In the meantime you can pay via M-Pesa Paybill 400400 (Acc: SILVERLAKE)
        or reach us on WhatsApp to arrange payment.
      </div>
    </div>

    <div v-else-if="step === 'paying'" class="mt-10 rounded-xl border border-navy-800 bg-navy-900 p-6 text-center">
      <h2 class="font-[Georgia] text-xl font-bold text-gold-400">Check your phone</h2>
      <p class="mt-2 text-sm text-slate-300">
        We've sent an M-Pesa prompt to {{ form.customer_phone }}. Enter your PIN to complete payment for booking
        #{{ booking?.id }}.
      </p>
    </div>
  </div>
</template>
