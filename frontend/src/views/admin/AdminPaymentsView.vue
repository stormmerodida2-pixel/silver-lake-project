<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'

const { items: payments, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/payments/')
const busyId = ref(null)

const methodBadge = {
  mpesa: 'bg-emerald-500/10 text-emerald-400',
  cash: 'bg-gold-500/10 text-gold-400',
  card: 'bg-brand-blue-500/10 text-brand-blue-400',
}

const statusBadge = {
  successful: 'bg-emerald-500/10 text-emerald-400',
  pending: 'bg-navy-800 text-slate-400',
  failed: 'bg-red-500/10 text-red-400',
}

async function remindDriver(payment) {
  busyId.value = payment.id
  try {
    const { data } = await apiClient.post(`/payments/${payment.id}/remind/`)
    Object.assign(payment, data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not send a reminder for this payment.'
  } finally {
    busyId.value = null
  }
}

function remindDisabledReason(payment) {
  if (payment.status !== 'pending' || !payment.recorded_by_driver_name) return null
  if (!payment.last_reminded_at) return null
  const elapsedMs = Date.now() - new Date(payment.last_reminded_at).getTime()
  return elapsedMs < 60 * 60 * 1000 ? 'Reminded recently - please wait before sending another.' : null
}

function needsDeposit(payment) {
  return payment.method === 'cash' && payment.status === 'successful' && !payment.cash_deposit
}

async function remindDeposit(payment) {
  busyId.value = payment.id
  try {
    const { data } = await apiClient.post(`/payments/${payment.id}/remind-deposit/`)
    Object.assign(payment, data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not send a deposit reminder for this payment.'
  } finally {
    busyId.value = null
  }
}

function remindDepositDisabledReason(payment) {
  if (!needsDeposit(payment) || !payment.recorded_by_driver_name) return null
  if (!payment.last_reminded_at) return null
  const elapsedMs = Date.now() - new Date(payment.last_reminded_at).getTime()
  return elapsedMs < 60 * 60 * 1000 ? 'Reminded recently - please wait before sending another.' : null
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="font-[Georgia] text-2xl font-bold text-white">Payments</h1>
    <p class="mt-1 text-sm text-slate-400">
      Every payment recorded against a booking - M-Pesa, card, or cash a driver reported on-site.
    </p>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <div v-if="!loading" class="mt-6 overflow-x-auto rounded-xl border border-navy-800">
      <table class="w-full text-left text-sm">
        <thead class="bg-navy-900 text-slate-400">
          <tr>
            <th class="px-4 py-3">Booking</th>
            <th class="px-4 py-3">Method</th>
            <th class="px-4 py-3">Amount</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Reference</th>
            <th class="px-4 py-3">Recorded By</th>
            <th class="px-4 py-3">Paybill Deposit</th>
            <th class="px-4 py-3">Date</th>
            <th class="px-4 py-3">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-navy-800 bg-navy-950">
          <tr v-for="payment in payments" :key="payment.id">
            <td class="px-4 py-3 text-white">#{{ payment.booking }}</td>
            <td class="px-4 py-3">
              <span class="rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="methodBadge[payment.method]">
                {{ payment.method === 'mpesa' ? 'M-Pesa' : payment.method.charAt(0).toUpperCase() + payment.method.slice(1) }}
              </span>
            </td>
            <td class="px-4 py-3 text-slate-300">KES {{ Number(payment.amount).toLocaleString() }}</td>
            <td class="px-4 py-3">
              <div class="flex flex-wrap items-center gap-1.5">
                <span class="rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="statusBadge[payment.status]">
                  {{ payment.status }}
                </span>
                <span
                  v-if="payment.is_disputed"
                  class="rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs font-semibold text-red-400"
                  :title="payment.dispute_note"
                >
                  ⚠ Disputed
                </span>
              </div>
            </td>
            <td class="px-4 py-3 text-xs text-slate-400">
              {{ payment.mpesa_receipt_number || payment.card_transaction_ref || '—' }}
            </td>
            <td class="px-4 py-3 text-xs text-slate-400">
              {{ payment.recorded_by_driver_name || '—' }}
              <div v-if="payment.note" class="italic text-slate-500">{{ payment.note }}</div>
            </td>
            <td class="px-4 py-3 text-xs">
              <template v-if="payment.method === 'cash'">
                <template v-if="payment.cash_deposit">
                  <span class="font-semibold text-emerald-400">KES {{ Number(payment.cash_deposit.amount).toLocaleString() }}</span>
                  <div class="text-slate-500">{{ payment.cash_deposit.mpesa_reference }}</div>
                </template>
                <span v-else-if="payment.status === 'successful'" class="font-semibold text-gold-400">⚠ Not deposited yet</span>
                <span v-else class="text-slate-600">—</span>
              </template>
              <span v-else class="text-slate-600">—</span>
            </td>
            <td class="px-4 py-3 text-xs text-slate-500">{{ new Date(payment.created_at).toLocaleString() }}</td>
            <td class="px-4 py-3">
              <button
                v-if="payment.status === 'pending' && payment.recorded_by_driver_name"
                :disabled="busyId === payment.id || !!remindDisabledReason(payment)"
                :title="remindDisabledReason(payment) || ''"
                class="rounded-md border border-navy-700 px-2.5 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="remindDriver(payment)"
              >
                {{ busyId === payment.id ? 'Sending...' : (payment.last_reminded_at ? 'Remind Again' : 'Remind Driver') }}
              </button>
              <button
                v-else-if="needsDeposit(payment) && payment.recorded_by_driver_name"
                :disabled="busyId === payment.id || !!remindDepositDisabledReason(payment)"
                :title="remindDepositDisabledReason(payment) || ''"
                class="rounded-md border border-navy-700 px-2.5 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="remindDeposit(payment)"
              >
                {{ busyId === payment.id ? 'Sending...' : (payment.last_reminded_at ? 'Remind Again' : 'Remind Deposit') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!payments.length" class="p-6 text-center text-slate-400">No payments yet.</p>
      <div v-if="nextUrl" class="border-t border-navy-800 p-3 text-center">
        <button
          :disabled="loadingMore"
          class="rounded-md border border-navy-700 px-4 py-1.5 text-sm font-medium text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
          @click="loadMore"
        >
          {{ loadingMore ? 'Loading...' : 'Load More' }}
        </button>
      </div>
    </div>
  </div>
</template>
