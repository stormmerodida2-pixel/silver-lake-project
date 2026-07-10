<script setup>
import { computed, onMounted, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const { items: payouts, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/payouts/')
const busyId = ref(null)
const filter = ref('pending') // 'pending' | 'paid' | 'all'

const filteredPayouts = computed(() => {
  if (filter.value === 'all') return payouts.value
  return payouts.value.filter((p) => (filter.value === 'paid' ? p.is_paid : !p.is_paid))
})

async function markPaid(payout) {
  const reference = window.prompt('M-Pesa/bank reference for this payout (optional):', '')
  if (reference === null) return
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
  const note = window.prompt(
    'How was this reconciled? (required - e.g. "Called customer, confirmed KES 5000 received")',
    '',
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

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between">
      <h1 class="font-[Georgia] text-2xl font-bold text-white">Driver Payouts</h1>
      <RouterLink to="/admin" class="text-sm font-semibold text-gold-400 hover:text-gold-300">
        See totals on Dashboard &rarr;
      </RouterLink>
    </div>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <template v-if="!loading">
      <div class="mt-4 flex gap-2">
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

      <div class="mt-4 overflow-x-auto rounded-xl border border-navy-800">
        <table class="w-full text-left text-sm">
          <thead class="bg-navy-900 text-slate-400">
            <tr>
              <th class="px-4 py-3">Driver</th>
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
              <td class="px-4 py-3 text-white">{{ payout.driver_name }}</td>
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
                  <button
                    v-else-if="auth.user?.is_superuser"
                    :disabled="busyId === payout.id || (payout.needs_verification && !payout.is_verified)"
                    class="rounded-md bg-gold-500 px-2 py-1 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                    @click="markPaid(payout)"
                  >
                    Mark Paid
                  </button>
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
