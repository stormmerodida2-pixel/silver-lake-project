<script setup>
import { computed, onMounted, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'
import { confirmDialog, promptDialog } from '../../utils/dialogs'

const auth = useAuthStore()
const { items: refunds, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/refunds/')
const busyId = ref(null)
const filter = ref('pending') // 'pending' | 'issued' | 'all'

const filteredRefunds = computed(() => {
  if (filter.value === 'all') return refunds.value
  return refunds.value.filter((r) => r.status === filter.value)
})

async function markIssued(refund) {
  const reference = await promptDialog('M-Pesa/bank reference used to send this refund (optional):')
  if (reference === null) return
  busyId.value = refund.id
  try {
    const { data } = await apiClient.post(`/admin/refunds/${refund.id}/mark-issued/`, { reference })
    Object.assign(refund, data)
  } catch (err) {
    error.value = 'Could not mark this refund as issued.'
  } finally {
    busyId.value = null
  }
}

// A refund is "pending B2C" the moment Safaricom accepts the disbursement request, until its own
// result callback confirms either way (see payments.services.initiate_refund_disbursement /
// payments.views.mpesa_b2c_result) - status stays 'pending' the whole time, so this is the only
// way to tell "waiting on Safaricom" apart from "never attempted."
function isB2cPending(refund) {
  return !!refund.b2c_conversation_id && refund.status !== 'issued' && !refund.b2c_failed_at
}

async function disburseRefund(refund) {
  if (!(await confirmDialog(`Send KES ${Number(refund.amount).toLocaleString()} to ${refund.recipient_phone_number} via M-Pesa now?`))) return
  busyId.value = refund.id
  try {
    const { data } = await apiClient.post(`/admin/refunds/${refund.id}/disburse/`)
    Object.assign(refund, data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not start this M-Pesa disbursement.'
  } finally {
    busyId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between">
      <h1 class="font-[Georgia] text-2xl font-bold text-white">Refunds</h1>
      <RouterLink to="/admin/bookings" class="text-sm font-semibold text-gold-400 hover:text-gold-300">
        View bookings &rarr;
      </RouterLink>
    </div>
    <p class="mt-1 text-sm text-slate-400">
      Created automatically whenever a booking with money already paid against it gets cancelled.
    </p>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <template v-if="!loading">
      <div class="mt-4 flex gap-2">
        <button
          v-for="option in ['pending', 'issued', 'all']"
          :key="option"
          class="rounded-md border px-3 py-1.5 text-sm font-medium transition"
          :class="
            filter === option
              ? 'border-gold-500 bg-gold-500 text-navy-950'
              : 'border-navy-700 text-slate-300 hover:border-gold-400 hover:text-gold-400'
          "
          @click="filter = option"
        >
          {{ option.charAt(0).toUpperCase() + option.slice(1) }}
        </button>
      </div>

      <div class="mt-4 overflow-x-auto rounded-xl border border-navy-800">
        <table class="w-full text-left text-sm">
          <thead class="bg-navy-900 text-slate-400">
            <tr>
              <th class="px-4 py-3">Booking</th>
              <th class="px-4 py-3">Customer</th>
              <th class="px-4 py-3">Amount</th>
              <th class="px-4 py-3">Status</th>
              <th class="px-4 py-3">Reference</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-navy-800 bg-navy-950">
            <tr v-for="refund in filteredRefunds" :key="refund.id">
              <td class="px-4 py-3 text-white">#{{ refund.booking_id }}</td>
              <td class="px-4 py-3 text-slate-300">{{ refund.customer_name }}</td>
              <td class="px-4 py-3 text-slate-300">KES {{ Number(refund.amount).toLocaleString() }}</td>
              <td class="px-4 py-3">
                <div class="flex flex-col gap-1">
                  <span :class="refund.status === 'issued' ? 'text-gold-400' : 'text-red-400'">
                    {{ refund.status === 'issued' ? 'Issued' : 'Pending' }}
                  </span>
                  <span
                    v-if="isB2cPending(refund)"
                    class="inline-flex w-fit items-center gap-1.5 rounded-full bg-brand-blue-500/10 px-2 py-0.5 text-xs font-semibold text-brand-blue-400"
                    title="Sent to M-Pesa - waiting for Safaricom to confirm it landed"
                  >
                    M-Pesa Disbursement Pending
                  </span>
                  <span
                    v-else-if="refund.b2c_failed_at"
                    class="inline-flex w-fit items-center gap-1.5 rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-semibold text-red-400"
                    :title="refund.notes"
                  >
                    ⚠ M-Pesa Disbursement Failed
                  </span>
                </div>
              </td>
              <td class="px-4 py-3 text-slate-400">{{ refund.reference || '-' }}</td>
              <td class="px-4 py-3">
                <div v-if="refund.status !== 'issued' && auth.user?.is_superuser" class="flex flex-col items-start gap-1.5">
                  <button
                    :disabled="busyId === refund.id"
                    class="rounded-md bg-gold-500 px-2 py-1 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                    @click="markIssued(refund)"
                  >
                    Mark Issued
                  </button>
                  <button
                    v-if="refund.recipient_phone_number && !isB2cPending(refund)"
                    :disabled="busyId === refund.id"
                    class="rounded-md border border-brand-blue-500 px-2 py-1 text-xs font-semibold text-brand-blue-400 hover:bg-brand-blue-500 hover:text-white disabled:opacity-50"
                    @click="disburseRefund(refund)"
                  >
                    {{ refund.b2c_failed_at ? 'Retry via M-Pesa' : 'Disburse via M-Pesa' }}
                  </button>
                </div>
                <span v-else-if="refund.status !== 'issued'" class="text-xs text-slate-500">Superadmin only</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!filteredRefunds.length" class="p-6 text-center text-slate-400">No refunds in this view.</p>
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
    </template>
  </div>
</template>
