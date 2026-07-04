<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import apiClient from '../api/client'

const route = useRoute()

const booking = ref(null)
const loading = ref(true)
const loadError = ref('')

const phoneNumber = ref('')
const payOption = ref('deposit') // 'deposit' | 'full'
const submitting = ref(false)
const error = ref('')
const requested = ref(false)

async function loadBooking() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await apiClient.get(`/pay/${route.params.token}/`)
    booking.value = data
  } catch (err) {
    loadError.value = 'This payment link is invalid or has expired.'
  } finally {
    loading.value = false
  }
}

const amountToPay = computed(() => {
  if (!booking.value) return 0
  return payOption.value === 'full' ? Number(booking.value.balance_due) : Number(booking.value.deposit_amount)
})

async function payWithMpesa() {
  submitting.value = true
  error.value = ''
  try {
    await apiClient.post(`/pay/${route.params.token}/stk-push/`, {
      phone_number: phoneNumber.value,
      amount: amountToPay.value,
    })
    requested.value = true
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not start M-Pesa payment. You can also pay via Paybill 400400 (Acc: SILVERLAKE).'
  } finally {
    submitting.value = false
  }
}

onMounted(loadBooking)
</script>

<template>
  <div class="min-h-screen bg-white">
    <div class="mx-auto max-w-lg px-4 py-16 sm:px-6">
      <div class="text-center">
        <h1 class="font-[Georgia] text-2xl font-bold text-navy-900">Pay for Your Trip</h1>
        <p class="mt-2 text-sm text-slate-500">SilverLake Car Rentals</p>
      </div>

      <p v-if="loading" class="mt-10 text-center text-slate-500">Loading...</p>
      <div v-else-if="loadError" class="mt-10 rounded-xl border border-red-200 bg-red-50 p-6 text-center text-red-700">
        {{ loadError }}
      </div>

      <template v-else-if="booking">
        <div class="mt-8 rounded-2xl border border-slate-200 bg-slate-50 p-6">
          <p class="text-sm text-slate-500">Booking for</p>
          <h2 class="font-[Georgia] text-lg font-bold text-navy-900">{{ booking.customer_name }}</h2>
          <p class="mt-1 text-sm text-slate-600">
            {{ booking.vehicle_name }}<span v-if="booking.driver_name"> &middot; Driver: {{ booking.driver_name }}</span>
          </p>
          <p class="text-sm text-slate-500">{{ booking.start_date }} to {{ booking.end_date }}</p>

          <div class="mt-4 space-y-1 border-t border-slate-200 pt-4 text-sm">
            <div class="flex justify-between text-slate-600">
              <span>Total</span>
              <span>KES {{ Number(booking.total_amount).toLocaleString() }}</span>
            </div>
            <div class="flex justify-between text-slate-600">
              <span>Paid so far</span>
              <span>KES {{ Number(booking.amount_paid).toLocaleString() }}</span>
            </div>
            <div class="flex justify-between text-base font-bold text-navy-900">
              <span>Balance Due</span>
              <span class="text-gold-500">KES {{ Number(booking.balance_due).toLocaleString() }}</span>
            </div>
          </div>
        </div>

        <div v-if="booking.status === 'cancelled'" class="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
          This booking has been cancelled.
        </div>
        <div v-else-if="Number(booking.balance_due) <= 0" class="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-6 text-center text-emerald-700">
          This booking is fully paid. Thank you!
        </div>

        <div v-else-if="requested" class="mt-6 rounded-2xl border border-slate-200 bg-slate-50 p-6 text-center">
          <h2 class="font-[Georgia] text-lg font-bold text-brand-blue-600">Check your phone</h2>
          <p class="mt-2 text-sm text-slate-600">
            We've sent an M-Pesa prompt to {{ phoneNumber }}. Enter your PIN to complete payment.
          </p>
        </div>

        <div v-else class="mt-6 space-y-4 rounded-2xl border border-slate-200 bg-slate-50 p-6">
          <div v-if="!booking.is_deposit_paid">
            <label class="mb-1 block text-sm text-slate-600">How much would you like to pay now?</label>
            <div class="grid grid-cols-2 gap-3">
              <button
                type="button"
                class="rounded-md border px-3 py-2 text-sm font-semibold"
                :class="payOption === 'deposit' ? 'border-brand-blue-600 bg-brand-blue-600 text-white' : 'border-slate-300 text-slate-600'"
                @click="payOption = 'deposit'"
              >
                Deposit (30%)<br />
                <span class="text-xs font-normal">KES {{ Number(booking.deposit_amount).toLocaleString() }}</span>
              </button>
              <button
                type="button"
                class="rounded-md border px-3 py-2 text-sm font-semibold"
                :class="payOption === 'full' ? 'border-brand-blue-600 bg-brand-blue-600 text-white' : 'border-slate-300 text-slate-600'"
                @click="payOption = 'full'"
              >
                Pay in Full<br />
                <span class="text-xs font-normal">KES {{ Number(booking.balance_due).toLocaleString() }}</span>
              </button>
            </div>
          </div>
          <div v-else class="text-sm text-slate-600">
            Deposit already paid - paying the remaining balance of
            KES {{ Number(booking.balance_due).toLocaleString() }}.
          </div>

          <div>
            <label class="mb-1 block text-sm text-slate-600">M-Pesa Phone Number</label>
            <input
              v-model="phoneNumber"
              type="tel"
              placeholder="2547XXXXXXXX"
              required
              class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
            />
          </div>

          <p v-if="error" class="text-sm text-red-600">{{ error }}</p>

          <button
            :disabled="submitting || !phoneNumber"
            class="w-full rounded-md bg-gold-500 px-4 py-2.5 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
            @click="payWithMpesa"
          >
            {{ submitting ? 'Sending prompt...' : `Pay KES ${amountToPay.toLocaleString()} via M-Pesa` }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
