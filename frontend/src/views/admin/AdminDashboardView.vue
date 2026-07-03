<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../../api/client'

const stats = ref(null)
const loading = ref(true)
const error = ref('')

function fmt(amount) {
  return `KES ${Number(amount || 0).toLocaleString()}`
}

const statusLabels = {
  pending: 'Pending',
  confirmed: 'Confirmed',
  ongoing: 'Ongoing',
  completed: 'Completed',
  cancelled: 'Cancelled',
}

onMounted(async () => {
  try {
    const { data } = await apiClient.get('/admin/stats/')
    stats.value = data
  } catch (err) {
    error.value = 'Could not load dashboard stats.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <p v-if="loading" class="text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="text-center text-red-400">{{ error }}</p>

    <div v-else class="space-y-10">
      <section class="rounded-2xl border border-gold-500/40 bg-gradient-to-br from-navy-900 to-navy-950 p-6 sm:p-8">
        <p class="text-sm font-semibold uppercase tracking-wide text-gold-400">Total Revenue Collected</p>
        <p class="mt-2 font-[Georgia] text-4xl font-bold text-white sm:text-5xl">
          {{ fmt(stats.revenue.total_collected) }}
        </p>
        <p class="mt-2 text-sm text-slate-400">
          {{ fmt(stats.revenue.collected_this_month) }} collected this month
        </p>
      </section>

      <section>
        <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Revenue Breakdown</h2>
        <div class="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div class="rounded-xl border border-navy-800 bg-navy-900 p-5">
            <p class="text-sm text-slate-400">Platform Fees Earned</p>
            <p class="mt-1 text-2xl font-bold text-gold-400">{{ fmt(stats.revenue.platform_fees_earned) }}</p>
            <p class="mt-1 text-xs text-slate-500">SilverLake's cut of with-driver bookings</p>
          </div>
          <div class="rounded-xl border border-navy-800 bg-navy-900 p-5">
            <p class="text-sm text-slate-400">Driver Payouts Owed</p>
            <p class="mt-1 text-2xl font-bold text-red-400">{{ fmt(stats.revenue.driver_payouts_owed) }}</p>
            <p class="mt-1 text-xs text-slate-500">Not yet disbursed to drivers</p>
          </div>
          <div class="rounded-xl border border-navy-800 bg-navy-900 p-5">
            <p class="text-sm text-slate-400">Driver Payouts Paid</p>
            <p class="mt-1 text-2xl font-bold text-white">{{ fmt(stats.revenue.driver_payouts_paid) }}</p>
            <p class="mt-1 text-xs text-slate-500">Already disbursed to drivers</p>
          </div>
        </div>
      </section>

      <section>
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Bookings by Status</h2>
          <RouterLink to="/admin/bookings" class="text-sm font-semibold text-gold-400 hover:text-gold-300">
            View all {{ stats.bookings.total }} &rarr;
          </RouterLink>
        </div>
        <div class="mt-3 grid gap-4 sm:grid-cols-3 lg:grid-cols-5">
          <div
            v-for="(label, key) in statusLabels"
            :key="key"
            class="rounded-xl border border-navy-800 bg-navy-900 p-4 text-center"
          >
            <p class="text-sm text-slate-400">{{ label }}</p>
            <p class="mt-1 text-xl font-bold text-white">{{ stats.bookings.by_status[key] || 0 }}</p>
          </div>
        </div>
      </section>

      <section>
        <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Users &amp; Drivers</h2>
        <div class="mt-3 grid gap-4 sm:grid-cols-3">
          <RouterLink
            to="/admin/users"
            class="rounded-xl border border-navy-800 bg-navy-900 p-5 transition hover:border-gold-400"
          >
            <p class="text-sm text-slate-400">Total Users</p>
            <p class="mt-1 text-2xl font-bold text-white">{{ stats.users.total }}</p>
            <p class="text-xs text-slate-500">{{ stats.users.new_last_7_days }} new in last 7 days</p>
          </RouterLink>
          <RouterLink
            to="/admin/users"
            class="rounded-xl border border-navy-800 bg-navy-900 p-5 transition hover:border-gold-400"
          >
            <p class="text-sm text-slate-400">Active Users</p>
            <p class="mt-1 text-2xl font-bold text-white">{{ stats.users.active }}</p>
          </RouterLink>
          <RouterLink
            to="/admin/drivers"
            class="rounded-xl border p-5 transition"
            :class="
              stats.drivers.pending_applications
                ? 'border-gold-500 bg-navy-900 hover:border-gold-400'
                : 'border-navy-800 bg-navy-900 hover:border-gold-400'
            "
          >
            <p class="text-sm text-slate-400">Pending Driver Applications</p>
            <p class="mt-1 text-2xl font-bold" :class="stats.drivers.pending_applications ? 'text-gold-400' : 'text-white'">
              {{ stats.drivers.pending_applications }}
            </p>
            <p class="text-xs font-semibold text-gold-400">Review &rarr;</p>
          </RouterLink>
        </div>
      </section>
    </div>
  </div>
</template>
