<script setup>
import { useRouter } from 'vue-router'

import { useDriverPortalStore } from '../../stores/driverPortal'

const router = useRouter()
const driverPortal = useDriverPortalStore()
</script>

<template>
  <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
    <button
      class="rounded-xl border border-navy-800 bg-navy-900 p-4 text-left transition hover:border-gold-400"
      @click="router.push('/driver/vehicles')"
    >
      <p class="text-xs text-slate-400">Live Vehicles</p>
      <p class="mt-1 text-xl font-bold text-white">{{ driverPortal.profile.vehicles.length }}</p>
    </button>
    <button
      class="rounded-xl border p-4 text-left transition"
      :class="
        driverPortal.serviceDueCount ? 'border-gold-500 hover:border-gold-400' : 'border-navy-800 hover:border-gold-400'
      "
      @click="router.push('/driver/vehicles')"
    >
      <p class="text-xs text-slate-400">Service Due</p>
      <p class="mt-1 text-xl font-bold" :class="driverPortal.serviceDueCount ? 'text-gold-400' : 'text-white'">
        {{ driverPortal.serviceDueCount }}
      </p>
    </button>
    <button
      class="rounded-xl border p-4 text-left transition"
      :class="
        driverPortal.pendingBookingsCount
          ? 'border-gold-500 hover:border-gold-400'
          : 'border-navy-800 hover:border-gold-400'
      "
      @click="router.push('/driver/bookings')"
    >
      <p class="text-xs text-slate-400">Awaiting Approval</p>
      <p class="mt-1 text-xl font-bold" :class="driverPortal.pendingBookingsCount ? 'text-gold-400' : 'text-white'">
        {{ driverPortal.pendingBookingsCount }}
      </p>
    </button>
    <button
      class="rounded-xl border border-navy-800 bg-navy-900 p-4 text-left transition hover:border-gold-400"
      @click="router.push('/driver/bookings')"
    >
      <p class="text-xs text-slate-400">Active Trips</p>
      <p class="mt-1 text-xl font-bold text-white">{{ driverPortal.activeTripsCount }}</p>
    </button>
    <button
      class="rounded-xl border border-navy-800 bg-navy-900 p-4 text-left transition hover:border-gold-400"
      @click="router.push('/driver/bookings')"
    >
      <p class="text-xs text-slate-400">Completed Trips</p>
      <p class="mt-1 text-xl font-bold text-white">{{ driverPortal.completedTripsCount }}</p>
    </button>
  </div>
</template>
