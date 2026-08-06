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
  const reference = await promptDialog(
    'M-Pesa/bank reference used to send this refund (required - at least the last 4 digits/characters):',
  )
  if (reference === null) return
  if (reference.trim().length < 4) {
    error.value = 'Enter the transaction reference used to send this refund (at least 4 digits/characters).'
    return
  }
  busyId.value = refund.id
  try {
    const { data } = await apiClient.post(`/admin/refunds/${refund.id}/mark-issued/`, { reference })
    Object.assign(refund, data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not mark this refund as issued.'
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
  if (
    !(await confirmDialog(
      `Send KES ${Number(refund.amount).toLocaleString()} to ${refund.recipient_phone_number} via M-Pesa now?`,
    ))
  )
    return
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
      <h1 class="font-[Georgia] text-2xl font-bold text-foreground">Refunds</h1>
      <RouterLink to="/admin/bookings" class="text-sm font-semibold text-accent hover:text-accent-strong">
        View bookings &rarr;
      </RouterLink>
    </div>
    <p class="mt-1 text-sm text-foreground-muted">
      Created automatically whenever a booking with money already paid against it gets cancelled.
    </p>

    <p v-if="loading" class="mt-10 text-center text-foreground-muted">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-danger">{{ error }}</p>

    <template v-if="!loading">
      <div class="mt-4 flex gap-2">
        <button
          v-for="option in ['pending', 'issued', 'all']"
          :key="option"
          class="rounded-md border px-3 py-1.5 text-sm font-medium transition"
          :class="
            filter === option
              ? 'border-accent-border-strong bg-accent-bg text-on-accent'
              : 'border-border text-foreground-secondary hover:border-accent-border hover:text-accent'
          "
          @click="filter = option"
        >
          {{ option.charAt(0).toUpperCase() + option.slice(1) }}
        </button>
      </div>

      <div class="mt-4 overflow-x-auto rounded-xl border border-border-subtle">
        <table class="w-full text-left text-sm">
          <thead class="bg-surface text-foreground-muted">
            <tr>
              <th class="px-4 py-3">Booking</th>
              <th class="px-4 py-3">Customer</th>
              <th class="px-4 py-3">Amount</th>
              <th class="px-4 py-3">Status</th>
              <th class="px-4 py-3">Reference</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border-subtle bg-page">
            <tr v-for="refund in filteredRefunds" :key="refund.id">
              <td class="px-4 py-3 text-foreground">#{{ refund.booking_id }}</td>
              <td class="px-4 py-3 text-foreground-secondary">{{ refund.customer_name }}</td>
              <td class="px-4 py-3 text-foreground-secondary">KES {{ Number(refund.amount).toLocaleString() }}</td>
              <td class="px-4 py-3">
                <div class="flex flex-col gap-1">
                  <span :class="refund.status === 'issued' ? 'text-accent' : 'text-danger'">
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
                    class="inline-flex w-fit items-center gap-1.5 rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-semibold text-danger"
                    :title="refund.notes"
                  >
                    ⚠ M-Pesa Disbursement Failed
                  </span>
                </div>
              </td>
              <td class="px-4 py-3 text-foreground-muted">
                {{ refund.reference || '-' }}
                <span
                  v-if="refund.reference_reused"
                  class="ml-1 cursor-help text-accent"
                  title="This reference has been used on another refund too - could be a coincidental match or a real duplicate (e.g. an accidentally reused reference). Double-check before relying on it."
                >
                  ⚠
                </span>
              </td>
              <td class="px-4 py-3">
                <div
                  v-if="refund.status !== 'issued' && auth.user?.is_superuser"
                  class="flex flex-col items-start gap-1.5"
                >
                  <button
                    :disabled="busyId === refund.id"
                    class="rounded-md bg-accent-bg px-2 py-1 text-xs font-semibold text-on-accent hover:bg-accent-bg-hover disabled:opacity-50"
                    @click="markIssued(refund)"
                  >
                    Mark Issued
                  </button>
                  <button
                    v-if="refund.recipient_phone_number && !isB2cPending(refund)"
                    :disabled="busyId === refund.id"
                    class="rounded-md border border-brand-blue-500 px-2 py-1 text-xs font-semibold text-brand-blue-400 hover:bg-brand-blue-500 hover:text-foreground disabled:opacity-50"
                    @click="disburseRefund(refund)"
                  >
                    {{ refund.b2c_failed_at ? 'Retry via M-Pesa' : 'Disburse via M-Pesa' }}
                  </button>
                </div>
                <span v-else-if="refund.status !== 'issued'" class="text-xs text-foreground-subtle">Superadmin only</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!filteredRefunds.length" class="p-6 text-center text-foreground-muted">No refunds in this view.</p>
        <div v-if="nextUrl" class="border-t border-border-subtle p-3 text-center">
          <button
            :disabled="loadingMore"
            class="rounded-md border border-border px-4 py-1.5 text-sm font-medium text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
            @click="loadMore"
          >
            {{ loadingMore ? 'Loading...' : 'Load More' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
