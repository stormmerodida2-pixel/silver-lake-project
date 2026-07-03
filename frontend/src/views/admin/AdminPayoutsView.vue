<script setup>
import { computed, onMounted, ref } from 'vue'

import apiClient from '../../api/client'

const payouts = ref([])
const loading = ref(true)
const error = ref('')
const busyId = ref(null)
const filter = ref('pending') // 'pending' | 'paid' | 'all'

const filteredPayouts = computed(() => {
  if (filter.value === 'all') return payouts.value
  return payouts.value.filter((p) => (filter.value === 'paid' ? p.is_paid : !p.is_paid))
})

const totalOwed = computed(() =>
  payouts.value.filter((p) => !p.is_paid).reduce((sum, p) => sum + Number(p.amount), 0)
)

async function loadPayouts() {
  loading.value = true
  try {
    const { data } = await apiClient.get('/admin/payouts/')
    payouts.value = data.results ?? data
  } catch (err) {
    error.value = 'Could not load payouts.'
  } finally {
    loading.value = false
  }
}

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
    error.value = 'Could not mark this payout as paid.'
  } finally {
    busyId.value = null
  }
}

onMounted(loadPayouts)
</script>

<template>
  <div>
    <h1 class="font-[Georgia] text-2xl font-bold text-white">Driver Payouts</h1>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <template v-if="!loading">
      <div class="mt-4 rounded-xl border border-gold-500/40 bg-navy-900 p-4">
        <p class="text-sm text-slate-400">Total Owed to Drivers (unpaid)</p>
        <p class="mt-1 text-2xl font-bold text-red-400">KES {{ totalOwed.toLocaleString() }}</p>
      </div>

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
              <th class="px-4 py-3">Amount</th>
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
                <span :class="payout.is_paid ? 'text-gold-400' : 'text-red-400'">
                  {{ payout.is_paid ? 'Paid' : 'Pending' }}
                </span>
              </td>
              <td class="px-4 py-3 text-slate-400">{{ payout.payout_reference || '-' }}</td>
              <td class="px-4 py-3">
                <button
                  v-if="!payout.is_paid"
                  :disabled="busyId === payout.id"
                  class="rounded-md bg-gold-500 px-2 py-1 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                  @click="markPaid(payout)"
                >
                  Mark Paid
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!filteredPayouts.length" class="p-6 text-center text-slate-400">No payouts in this view.</p>
      </div>
    </template>
  </div>
</template>
