<script setup>
import { computed, onMounted, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'
import { confirmDialog, promptDialog } from '../../utils/dialogs'

const auth = useAuthStore()
const { items: payouts, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/payouts/')
const busyId = ref(null)
const filter = ref('pending') // 'pending' | 'paid' | 'all'
// A payout's recipient is either an individual driver-partner or a FleetPartner organization
// (see DriverPayout.driver/.organization - exactly one is ever set) - this filter lets staff
// isolate one or the other, since the same ledger already tracks both together.
const recipientFilter = ref('all') // 'all' | 'drivers' | 'fleet'

const filteredPayouts = computed(() => {
  let result = payouts.value
  if (filter.value !== 'all') {
    result = result.filter((p) => (filter.value === 'paid' ? p.is_paid : !p.is_paid))
  }
  if (recipientFilter.value !== 'all') {
    result = result.filter((p) => (recipientFilter.value === 'fleet' ? !!p.organization_name : !!p.driver_name))
  }
  return result
})

async function markPaid(payout) {
  const reference = await promptDialog(
    'M-Pesa/bank reference for this payout (required - at least the last 4 digits/characters):',
  )
  if (reference === null) return
  if (reference.trim().length < 4) {
    error.value = 'Enter the transaction reference used to send this payout (at least 4 digits/characters).'
    return
  }
  busyId.value = payout.id
  try {
    const { data } = await apiClient.post(`/admin/payouts/${payout.id}/mark-paid/`, {
      payout_reference: reference,
    })
    Object.assign(payout, data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not mark this payout as paid.'
  } finally {
    busyId.value = null
  }
}

async function verifyPayout(payout) {
  const note = await promptDialog(
    'How was this reconciled? (required - e.g. "Called customer, confirmed KES 5000 received")',
  )
  if (note === null) return
  if (!note.trim()) {
    error.value = 'A reconciliation note is required to verify this payout.'
    return
  }
  busyId.value = payout.id
  try {
    const { data } = await apiClient.post(`/admin/payouts/${payout.id}/verify/`, { note })
    Object.assign(payout, data)
  } catch (err) {
    error.value = err.response?.data?.note?.[0] || 'Could not verify this payout.'
  } finally {
    busyId.value = null
  }
}

// A payout is "pending B2C" the moment Safaricom accepts the disbursement request, until its
// own result callback confirms either way (see payments.services.initiate_payout_disbursement /
// payments.views.mpesa_b2c_result) - is_paid stays false the whole time, so this is the only way
// to tell "waiting on Safaricom" apart from "never attempted."
function isB2cPending(payout) {
  return !!payout.b2c_conversation_id && !payout.is_paid && !payout.b2c_failed_at
}

async function disbursePayout(payout) {
  if (!(await confirmDialog(`Send KES ${Number(payout.amount).toLocaleString()} to ${payout.recipient_phone_number} via M-Pesa now?`))) return
  busyId.value = payout.id
  try {
    const { data } = await apiClient.post(`/admin/payouts/${payout.id}/disburse/`)
    Object.assign(payout, data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not start this M-Pesa disbursement.'
  } finally {
    busyId.value = null
  }
}

const exportingCsv = ref(false)
async function exportCsv() {
  exportingCsv.value = true
  try {
    const params = new URLSearchParams()
    if (recipientFilter.value !== 'all') params.set('recipient', recipientFilter.value === 'fleet' ? 'fleet' : 'driver')
    const response = await apiClient.get(`/admin/payouts/export/?${params}`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `SilverLake-Payouts-${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    error.value = 'Could not export payouts to CSV.'
  } finally {
    exportingCsv.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between">
      <h1 class="font-[Georgia] text-2xl font-bold text-white">Payouts</h1>
      <div class="flex items-center gap-4">
        <button
          :disabled="exportingCsv"
          class="rounded-md border border-navy-700 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
          @click="exportCsv"
        >
          {{ exportingCsv ? 'Exporting...' : 'Export CSV' }}
        </button>
        <RouterLink to="/admin" class="text-sm font-semibold text-gold-400 hover:text-gold-300">
          See totals on Dashboard &rarr;
        </RouterLink>
      </div>
    </div>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <template v-if="!loading">
      <div class="mt-4 flex flex-wrap items-center gap-4">
        <div class="flex gap-2">
          <button
            v-for="option in ['pending', 'paid', 'all']"
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
        <div class="flex items-center gap-2 border-l border-navy-800 pl-4">
          <span class="text-xs font-semibold uppercase tracking-wide text-slate-500">Recipient</span>
          <button
            v-for="option in [{ value: 'all', label: 'All' }, { value: 'drivers', label: 'Drivers' }, { value: 'fleet', label: 'Fleet Partners' }]"
            :key="option.value"
            class="rounded-md border px-3 py-1.5 text-sm font-medium transition"
            :class="
              recipientFilter === option.value
                ? 'border-brand-blue-500 bg-brand-blue-500 text-white'
                : 'border-navy-700 text-slate-300 hover:border-brand-blue-400 hover:text-brand-blue-400'
            "
            @click="recipientFilter = option.value"
          >
            {{ option.label }}
          </button>
        </div>
      </div>

      <div class="mt-4 overflow-x-auto rounded-xl border border-navy-800">
        <table class="w-full text-left text-sm">
          <thead class="bg-navy-900 text-slate-400">
            <tr>
              <th class="px-4 py-3">Recipient</th>
              <th class="px-4 py-3">Booking</th>
              <th class="px-4 py-3">Payout Amount</th>
              <th class="px-4 py-3">Booking Paid</th>
              <th class="px-4 py-3">Status</th>
              <th class="px-4 py-3">Reference</th>
              <th class="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-navy-800 bg-navy-950">
            <tr v-for="payout in filteredPayouts" :key="payout.id">
              <td class="px-4 py-3 text-white">
                {{ payout.driver_name || payout.organization_name }}
                <span v-if="payout.organization_name" class="ml-1 rounded-full bg-brand-blue-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand-blue-400">
                  Org
                </span>
              </td>
              <td class="px-4 py-3 text-slate-300">
                #{{ payout.booking_id }}
                <div class="text-xs text-slate-500">{{ payout.customer_name }}</div>
              </td>
              <td class="px-4 py-3 text-slate-300">KES {{ Number(payout.amount).toLocaleString() }}</td>
              <td class="px-4 py-3">
                <span class="text-slate-300">
                  KES {{ Number(payout.booking_amount_paid).toLocaleString() }} / {{ Number(payout.booking_total_amount).toLocaleString() }}
                </span>
                <div v-if="Number(payout.booking_balance_due) > 0" class="text-xs font-semibold text-red-400">
                  KES {{ Number(payout.booking_balance_due).toLocaleString() }} still owed
                </div>
              </td>
              <td class="px-4 py-3">
                <div class="flex flex-col gap-1">
                  <span :class="payout.is_paid ? 'text-gold-400' : 'text-red-400'">
                    {{ payout.is_paid ? 'Paid' : 'Pending' }}
                  </span>
                  <span
                    v-if="isB2cPending(payout)"
                    class="inline-flex w-fit items-center gap-1.5 rounded-full bg-brand-blue-500/10 px-2 py-0.5 text-xs font-semibold text-brand-blue-400"
                    title="Sent to M-Pesa - waiting for Safaricom to confirm it landed"
                  >
                    M-Pesa Disbursement Pending
                  </span>
                  <span
                    v-else-if="payout.b2c_failed_at"
                    class="inline-flex w-fit items-center gap-1.5 rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-semibold text-red-400"
                    :title="payout.notes"
                  >
                    ⚠ M-Pesa Disbursement Failed
                  </span>
                  <span
                    v-if="payout.needs_verification"
                    class="inline-flex w-fit items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold"
                    :class="payout.is_verified ? 'bg-emerald-500/10 text-emerald-400' : 'bg-gold-500/10 text-gold-400'"
                    :title="payout.is_verified ? payout.verification_note : 'Confirmed via a self-reported cash/card payment - not yet verified'"
                  >
                    {{ payout.is_verified ? 'Verified' : 'Needs Verification' }}
                  </span>
                  <span
                    v-if="payout.has_disputed_payment"
                    class="inline-flex w-fit items-center gap-1.5 rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-semibold text-red-400"
                    title="A customer has disputed a cash payment on this booking - resolve before verifying or paying."
                  >
                    ⚠ Disputed
                  </span>
                  <span
                    v-if="payout.has_undeposited_cash"
                    class="inline-flex w-fit items-center gap-1.5 rounded-full bg-gold-500/10 px-2 py-0.5 text-xs font-semibold text-gold-400"
                    title="The driver hasn't logged a matching Paybill deposit for a cash payment on this booking yet - required before this can be verified."
                  >
                    ⚠ Not Deposited
                  </span>
                </div>
              </td>
              <td class="px-4 py-3 text-slate-400">{{ payout.payout_reference || '-' }}</td>
              <td class="px-4 py-3">
                <template v-if="!payout.is_paid">
                  <button
                    v-if="payout.needs_verification && !payout.is_verified && auth.user?.is_superuser"
                    :disabled="busyId === payout.id || payout.has_undeposited_cash"
                    :title="payout.has_undeposited_cash ? 'Waiting on the driver to log a matching Paybill deposit first' : ''"
                    class="rounded-md border border-gold-500 px-2 py-1 text-xs font-semibold text-gold-400 hover:bg-gold-500 hover:text-navy-950 disabled:cursor-not-allowed disabled:opacity-50"
                    @click="verifyPayout(payout)"
                  >
                    Verify
                  </button>
                  <div v-else-if="auth.user?.is_superuser" class="flex flex-col items-start gap-1.5">
                    <button
                      :disabled="busyId === payout.id"
                      class="rounded-md bg-gold-500 px-2 py-1 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                      @click="markPaid(payout)"
                    >
                      Mark Paid
                    </button>
                    <button
                      v-if="payout.recipient_phone_number && !isB2cPending(payout)"
                      :disabled="busyId === payout.id"
                      class="rounded-md border border-brand-blue-500 px-2 py-1 text-xs font-semibold text-brand-blue-400 hover:bg-brand-blue-500 hover:text-white disabled:opacity-50"
                      @click="disbursePayout(payout)"
                    >
                      {{ payout.b2c_failed_at ? 'Retry via M-Pesa' : 'Disburse via M-Pesa' }}
                    </button>
                  </div>
                  <span v-else class="text-xs text-slate-500">Superadmin only</span>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!filteredPayouts.length" class="p-6 text-center text-slate-400">No payouts in this view.</p>
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
