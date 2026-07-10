<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
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
      <!-- Page title -->
      <h1 class="font-[Georgia] text-2xl font-bold text-white">Dashboard</h1>

      <!-- Prompts a freshly-invited account (see core.services.invite_staff_account) to fill in
           their name - registration only ever collects the organization's own details, never
           the actual person's, so this stays without them until they do. -->
      <RouterLink
        v-if="!auth.user?.first_name"
        to="/account/profile"
        class="flex items-center justify-between gap-3 rounded-2xl border border-gold-500/40 bg-gold-500/5 p-5 transition hover:border-gold-400"
      >
        <div>
          <p class="font-[Georgia] text-lg font-bold text-white">Welcome{{ auth.user?.organization_name ? ` to ${auth.user.organization_name}'s dashboard` : '' }}!</p>
          <p class="mt-1 text-sm text-slate-400">Complete your profile with your name and phone number to get started.</p>
        </div>
        <span class="shrink-0 rounded-lg bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950">Complete Profile</span>
      </RouterLink>

      <!-- A fresh organization (or, in principle, SilverLake's own account) with no vehicles on
           file yet can't receive a single booking - nudge straight to adding one. -->
      <RouterLink
        v-if="stats.fleet.total === 0"
        to="/admin/fleet"
        class="flex items-center justify-between gap-3 rounded-2xl border border-gold-500/40 bg-gold-500/5 p-5 transition hover:border-gold-400"
      >
        <div>
          <p class="font-[Georgia] text-lg font-bold text-white">Add your first vehicle</p>
          <p class="mt-1 text-sm text-slate-400">
            {{ auth.user?.organization_name ? 'Your fleet' : 'The fleet' }} is empty - add a vehicle to start receiving bookings.
          </p>
        </div>
        <span class="shrink-0 rounded-lg bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950">Add Vehicle</span>
      </RouterLink>

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
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Revenue Breakdown</h2>
          <RouterLink to="/admin/payouts" class="text-sm font-semibold text-gold-400 hover:text-gold-300">
            Manage payouts &rarr;
          </RouterLink>
        </div>
        <div class="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div class="rounded-xl border border-navy-800 bg-navy-900 p-5">
            <p class="text-sm text-slate-400">Platform Fees Earned</p>
            <p class="mt-1 text-2xl font-bold text-gold-400">{{ fmt(stats.revenue.platform_fees_earned) }}</p>
            <p class="mt-1 text-xs text-slate-500">SilverLake's cut of with-driver bookings</p>
          </div>
          <RouterLink
            to="/admin/payouts"
            class="rounded-xl border border-navy-800 bg-navy-900 p-5 transition hover:border-gold-400"
          >
            <p class="text-sm text-slate-400">Driver Payouts Owed</p>
            <p class="mt-1 text-2xl font-bold text-red-400">{{ fmt(stats.revenue.driver_payouts_owed) }}</p>
            <p class="mt-1 text-xs text-slate-500">Not yet disbursed to drivers</p>
          </RouterLink>
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
        <RouterLink
          to="/admin/bookings"
          class="mt-4 block rounded-xl border p-5 transition"
          :class="
            stats.bookings.needing_attention
              ? 'border-red-500/40 bg-red-500/5 hover:border-red-400'
              : 'border-navy-800 bg-navy-900 hover:border-gold-400'
          "
        >
          <p class="text-sm text-slate-400">Needing Attention</p>
          <p class="mt-1 text-2xl font-bold" :class="stats.bookings.needing_attention ? 'text-red-400' : 'text-white'">
            {{ stats.bookings.needing_attention }}
          </p>
          <p class="mt-1 text-xs text-slate-500">
            Past their scheduled end date but still open - nobody confirmed the trip started/ended,
            or it's unpaid.
          </p>
        </RouterLink>
      </section>

      <section>
        <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Users &amp; Drivers</h2>
        <div class="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
          <RouterLink
            to="/admin/drivers"
            class="rounded-xl border p-5 transition"
            :class="
              stats.drivers.away
                ? 'border-gold-500 bg-navy-900 hover:border-gold-400'
                : 'border-navy-800 bg-navy-900 hover:border-gold-400'
            "
          >
            <p class="text-sm text-slate-400">Drivers Away</p>
            <p class="mt-1 text-2xl font-bold" :class="stats.drivers.away ? 'text-gold-400' : 'text-white'">
              {{ stats.drivers.away }}
            </p>
            <p class="text-xs text-slate-500">Vehicles hidden from the public fleet</p>
          </RouterLink>
        </div>
      </section>

      <!-- Fleet stats -->
      <section>
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Fleet</h2>
          <RouterLink to="/admin/fleet" class="text-sm font-semibold text-gold-400 hover:text-gold-300">
            Manage fleet &rarr;
          </RouterLink>
        </div>
        <div class="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <RouterLink
            to="/admin/fleet"
            class="rounded-xl border border-navy-800 bg-navy-900 p-5 transition hover:border-gold-400"
          >
            <p class="text-sm text-slate-400">Total Vehicles</p>
            <p class="mt-1 text-2xl font-bold text-white">{{ stats.fleet.total }}</p>
          </RouterLink>
          <RouterLink
            to="/admin/fleet"
            class="rounded-xl border border-navy-800 bg-navy-900 p-5 transition hover:border-gold-400"
          >
            <p class="text-sm text-slate-400">Available</p>
            <p class="mt-1 text-2xl font-bold text-gold-400">{{ stats.fleet.available }}</p>
          </RouterLink>
          <RouterLink
            to="/admin/fleet"
            class="rounded-xl border border-navy-800 bg-navy-900 p-5 transition hover:border-gold-400"
          >
            <p class="text-sm text-slate-400">Unavailable</p>
            <p class="mt-1 text-2xl font-bold" :class="stats.fleet.unavailable ? 'text-red-400' : 'text-white'">
              {{ stats.fleet.unavailable }}
            </p>
          </RouterLink>
          <RouterLink
            to="/admin/fleet"
            class="rounded-xl border p-5 transition"
            :class="
              stats.fleet.service_due
                ? 'border-gold-500 bg-navy-900 hover:border-gold-400'
                : 'border-navy-800 bg-navy-900 hover:border-gold-400'
            "
          >
            <p class="text-sm text-slate-400">Service Due</p>
            <p class="mt-1 text-2xl font-bold" :class="stats.fleet.service_due ? 'text-gold-400' : 'text-white'">
              {{ stats.fleet.service_due }}
            </p>
            <p class="mt-1 text-xs text-slate-500">No service logged in 90+ days</p>
          </RouterLink>
        </div>
      </section>

      <!-- Fleet Partners (superadmin-only, empty for everyone else) -->
      <section v-if="stats.fleet_partners?.length">
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Fleet Partners</h2>
          <RouterLink to="/admin/fleet-partners" class="text-sm font-semibold text-gold-400 hover:text-gold-300">
            Manage partners &rarr;
          </RouterLink>
        </div>
        <div class="mt-3 overflow-x-auto rounded-xl border border-navy-800">
          <table class="w-full text-left text-sm">
            <thead class="bg-navy-900 text-slate-400">
              <tr>
                <th class="px-4 py-3">Partner</th>
                <th class="px-4 py-3">Vehicles</th>
                <th class="px-4 py-3">Bookings</th>
                <th class="px-4 py-3">Revenue</th>
                <th class="px-4 py-3">Collected</th>
                <th class="px-4 py-3">Platform Fee Earned</th>
                <th class="px-4 py-3">Payout Owed</th>
                <th class="px-4 py-3">Payout Paid</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-navy-800 bg-navy-950">
              <tr v-for="partner in stats.fleet_partners" :key="partner.id">
                <td class="px-4 py-3 font-medium text-white">{{ partner.name }}</td>
                <td class="px-4 py-3 text-slate-300">{{ partner.vehicle_count }}</td>
                <td class="px-4 py-3 text-slate-300">{{ partner.bookings_count }}</td>
                <td class="px-4 py-3 text-slate-300">{{ fmt(partner.total_revenue) }}</td>
                <td class="px-4 py-3 text-slate-300">{{ fmt(partner.total_collected) }}</td>
                <td class="px-4 py-3 font-semibold text-gold-400">{{ fmt(partner.platform_fee_earned) }}</td>
                <td class="px-4 py-3 font-semibold text-red-400">{{ fmt(partner.payout_owed) }}</td>
                <td class="px-4 py-3 text-slate-300">{{ fmt(partner.payout_paid) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="mt-2 text-xs text-slate-500">
          SilverLake keeps the Platform Fee as revenue; the rest is owed back to the partner via
          Admin → Payouts, same disbursement flow as an individual driver-partner's payout - money
          still lands in SilverLake's own Paybill either way (no per-partner routing is wired up).
        </p>
      </section>

      <!-- Reviews & Refunds stats -->
      <section>
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Reviews &amp; Refunds</h2>
        </div>
        <div class="mt-3 grid gap-4 sm:grid-cols-2">
          <RouterLink
            to="/admin/reviews"
            class="block rounded-xl border p-5 transition"
            :class="
              stats.reviews.pending
                ? 'border-gold-500 bg-navy-900 hover:border-gold-400'
                : 'border-navy-800 bg-navy-900 hover:border-gold-400'
            "
          >
            <p class="text-sm text-slate-400">Pending Reviews</p>
            <p
              class="mt-1 text-2xl font-bold"
              :class="stats.reviews.pending ? 'text-gold-400' : 'text-white'"
            >
              {{ stats.reviews.pending }}
            </p>
            <p class="mt-1 text-xs font-semibold text-gold-400">
              {{ stats.reviews.pending ? 'Needs your attention — Review &rarr;' : 'All reviews moderated ✓' }}
            </p>
          </RouterLink>
          <RouterLink
            to="/admin/refunds"
            class="block rounded-xl border p-5 transition"
            :class="
              stats.refunds.pending
                ? 'border-gold-500 bg-navy-900 hover:border-gold-400'
                : 'border-navy-800 bg-navy-900 hover:border-gold-400'
            "
          >
            <p class="text-sm text-slate-400">Pending Refunds</p>
            <p
              class="mt-1 text-2xl font-bold"
              :class="stats.refunds.pending ? 'text-gold-400' : 'text-white'"
            >
              {{ stats.refunds.pending }}
            </p>
            <p class="mt-1 text-xs font-semibold text-gold-400">
              {{ stats.refunds.pending ? 'Owed to customers — Manage &rarr;' : 'Nothing owed ✓' }}
            </p>
          </RouterLink>
        </div>
      </section>
    </div>
  </div>
</template>
