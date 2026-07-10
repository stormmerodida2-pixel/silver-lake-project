<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const { items: bookings, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/bookings/')
const { items: driverOptions, load: loadDriverOptions } = useAdminList('/admin/drivers/')
const busyId = ref(null)

const statusOptions = ['pending', 'confirmed', 'ongoing', 'completed', 'cancelled']

async function changeStatus(booking, newStatus) {
  if (newStatus === booking.status) return
  busyId.value = booking.id
  try {
    const { data } = await apiClient.post(`/admin/bookings/${booking.id}/set-status/`, { status: newStatus })
    Object.assign(booking, data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not update booking status.'
  } finally {
    busyId.value = null
  }
}

async function changeDriver(booking, driverId) {
  busyId.value = booking.id
  try {
    const { data } = await apiClient.patch(`/admin/bookings/${booking.id}/`, { driver: driverId || null })
    Object.assign(booking, data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not reassign driver.'
  } finally {
    busyId.value = null
  }
}

function isUnderpaid(booking) {
  return Number(booking.balance_due) > 0 && booking.status !== 'cancelled'
}

function canRemindBalance(booking) {
  return isUnderpaid(booking) && !!booking.driver_name
}

function balanceRemindDisabledReason(booking) {
  if (!booking.last_balance_reminder_at) return null
  const elapsedMs = Date.now() - new Date(booking.last_balance_reminder_at).getTime()
  return elapsedMs < 60 * 60 * 1000 ? 'Reminded recently - please wait before sending another.' : null
}

async function remindBalance(booking) {
  busyId.value = booking.id
  try {
    const { data } = await apiClient.post(`/admin/bookings/${booking.id}/remind_balance/`)
    Object.assign(booking, data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not send a reminder for this booking.'
  } finally {
    busyId.value = null
  }
}

onMounted(() => {
  load()
  loadDriverOptions()
})
</script>

<template>
  <div>
    <h1 class="font-[Georgia] text-2xl font-bold text-white">Manage Bookings</h1>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <div v-if="!loading" class="mt-6 overflow-x-auto rounded-xl border border-navy-800">
      <table class="w-full text-left text-sm">
        <thead class="bg-navy-900 text-slate-400">
          <tr>
            <th class="px-4 py-3">Customer</th>
            <th class="px-4 py-3">Vehicle</th>
            <th class="px-4 py-3">Service</th>
            <th class="px-4 py-3">Dates</th>
            <th class="px-4 py-3">Total</th>
            <th class="px-4 py-3">Paid</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Trip</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-navy-800 bg-navy-950">
          <tr
            v-for="booking in bookings"
            :key="booking.id"
            :class="booking.needs_attention ? 'bg-red-500/5' : ''"
          >
            <td class="px-4 py-3 text-white">
              {{ booking.customer_name }}
              <div class="text-xs text-slate-500">{{ booking.customer_phone }}</div>
              <span
                v-if="booking.source === 'driver_onsite'"
                class="mt-1 inline-block rounded-full bg-navy-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gold-400"
              >
                Walk-in
              </span>
            </td>
            <td class="px-4 py-3 text-slate-300">
              {{ booking.vehicle_name }}
            </td>
            <td class="px-4 py-3 text-slate-300">
              {{ booking.service_type === 'with_driver' ? 'With Driver' : 'Self Drive' }}
              <select
                v-if="booking.service_type === 'with_driver' && auth.user?.is_superuser"
                :value="booking.driver || ''"
                :disabled="busyId === booking.id"
                class="mt-1 block rounded-md border border-navy-700 bg-navy-950 px-2 py-1 text-xs text-white focus:border-gold-400 focus:outline-none disabled:opacity-50"
                @change="changeDriver(booking, $event.target.value ? Number($event.target.value) : null)"
              >
                <option value="">No driver assigned</option>
                <option v-for="d in driverOptions" :key="d.id" :value="d.id">{{ d.full_name }}</option>
              </select>
              <div v-else-if="booking.driver_name" class="text-xs text-slate-500">{{ booking.driver_name }}</div>
            </td>
            <td class="px-4 py-3 text-slate-400">{{ booking.start_date }} to {{ booking.end_date }}</td>
            <td class="px-4 py-3 text-slate-300">KES {{ Number(booking.total_amount).toLocaleString() }}</td>
            <td class="px-4 py-3 text-slate-300">
              KES {{ Number(booking.amount_paid).toLocaleString() }}
              <div v-if="isUnderpaid(booking)" class="mt-1">
                <div class="text-xs font-semibold text-red-400">
                  Balance due: KES {{ Number(booking.balance_due).toLocaleString() }}
                </div>
                <button
                  v-if="canRemindBalance(booking)"
                  :disabled="busyId === booking.id || !!balanceRemindDisabledReason(booking)"
                  :title="balanceRemindDisabledReason(booking) || ''"
                  class="mt-1 rounded-md border border-navy-700 px-2 py-0.5 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                  @click="remindBalance(booking)"
                >
                  {{ busyId === booking.id ? 'Sending...' : (booking.last_balance_reminder_at ? 'Remind Again' : 'Remind Driver') }}
                </button>
                <p v-else-if="!booking.driver_name" class="text-xs text-slate-600">No driver to remind</p>
              </div>
            </td>
            <td class="px-4 py-3">
              <select
                :value="booking.status"
                :disabled="busyId === booking.id"
                class="rounded-md border border-navy-700 bg-navy-950 px-2 py-1 text-xs text-white focus:border-gold-400 focus:outline-none disabled:opacity-50"
                @change="changeStatus(booking, $event.target.value)"
              >
                <option v-for="option in statusOptions" :key="option" :value="option">
                  {{ option.charAt(0).toUpperCase() + option.slice(1) }}
                </option>
              </select>
            </td>
            <td class="px-4 py-3 text-xs">
              <span
                v-if="booking.needs_attention"
                class="mb-1 inline-block rounded-full bg-red-500/10 px-2 py-0.5 font-semibold text-red-400"
              >
                Needs Attention
              </span>
              <div v-if="booking.trip_started_at" class="text-slate-500">Started {{ new Date(booking.trip_started_at).toLocaleDateString() }}</div>
              <div v-if="booking.trip_ended_at" class="text-slate-500">Ended {{ new Date(booking.trip_ended_at).toLocaleDateString() }}</div>
              <div v-if="!booking.trip_started_at && !booking.trip_ended_at && !booking.needs_attention" class="text-slate-600">—</div>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!bookings.length" class="p-6 text-center text-slate-400">No bookings yet.</p>
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
