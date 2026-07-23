<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import apiClient from '../api/client'

const route = useRoute()

const payment = ref(null)
const loading = ref(true)
const loadError = ref('')

const note = ref('')
const submitting = ref(false)
const submitError = ref('')
const submitted = ref(false)

function url() {
  return `/pay/${route.params.token}/payments/${route.params.paymentId}/dispute/`
}

async function loadPayment() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await apiClient.get(url())
    payment.value = data
  } catch {
    loadError.value = 'This dispute link is invalid, or this payment is not a cash payment that can be disputed.'
  } finally {
    loading.value = false
  }
}

async function submitDispute() {
  submitError.value = ''
  submitting.value = true
  try {
    await apiClient.post(url(), { note: note.value.trim() })
    submitted.value = true
  } catch {
    submitError.value = 'Could not record your dispute. Please try again, or contact us directly.'
  } finally {
    submitting.value = false
  }
}

onMounted(loadPayment)
</script>

<template>
  <div class="min-h-screen bg-white">
    <div class="mx-auto max-w-lg px-4 py-16 sm:px-6">
      <div class="text-center">
        <h1 class="font-[Georgia] text-2xl font-bold text-navy-900">Dispute a Cash Payment</h1>
        <p class="mt-2 text-sm text-slate-500">SilverLake Car Rentals</p>
      </div>

      <p v-if="loading" class="mt-10 text-center text-slate-500">Loading...</p>
      <div v-else-if="loadError" class="mt-10 rounded-xl border border-red-200 bg-red-50 p-6 text-center text-red-700">
        {{ loadError }}
      </div>

      <template v-else-if="payment">
        <div class="mt-8 rounded-2xl border border-slate-200 bg-slate-50 p-6">
          <p class="text-sm text-slate-500">Cash payment on booking #{{ payment.booking_id }}</p>
          <p class="mt-1 font-[Georgia] text-2xl font-bold text-navy-900">
            KES {{ Number(payment.amount).toLocaleString() }}
          </p>
          <p class="mt-1 text-xs text-slate-500">Recorded {{ new Date(payment.created_at).toLocaleString() }}</p>
        </div>

        <div
          v-if="submitted || payment.is_disputed"
          class="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-center"
        >
          <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
            <svg class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 class="mt-4 font-[Georgia] text-lg font-bold text-navy-900">Dispute Recorded</h2>
          <p class="mt-2 text-sm text-slate-600">
            This payment is on hold pending review. Our team will follow up with you directly.
          </p>
        </div>

        <div v-else class="mt-6 space-y-4 rounded-2xl border border-slate-200 bg-slate-50 p-6">
          <p class="text-sm text-slate-600">
            If you never made this payment, or the amount is wrong, let us know below. This will place the payment on
            hold until we've looked into it.
          </p>
          <div>
            <label class="mb-1 block text-sm text-slate-600">What happened? (optional)</label>
            <textarea
              v-model="note"
              rows="3"
              placeholder="e.g. I never paid this, or the amount I paid was different"
              class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 placeholder-slate-400 focus:border-brand-blue-500 focus:outline-none"
            ></textarea>
          </div>

          <p v-if="submitError" class="text-sm text-red-600">{{ submitError }}</p>

          <button
            :disabled="submitting"
            class="w-full rounded-md bg-gold-500 px-4 py-2.5 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
            @click="submitDispute"
          >
            {{ submitting ? 'Submitting...' : 'Dispute This Payment' }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
