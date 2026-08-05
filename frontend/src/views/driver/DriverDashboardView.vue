<script setup>
import { useRouter } from 'vue-router'

import { useDriverPortalStore } from '../../stores/driverPortal'

const router = useRouter()
const driverPortal = useDriverPortalStore()
</script>

<template>
  <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
    <button
      class="rounded-xl border border-border-subtle bg-surface p-4 text-left transition hover:border-accent-border"
      @click="router.push('/driver/vehicles')"
    >
      <p class="text-xs text-foreground-muted">Live Vehicles</p>
      <p class="mt-1 text-xl font-bold text-foreground">{{ driverPortal.profile.vehicles.length }}</p>
    </button>
    <button
      class="rounded-xl border p-4 text-left transition"
      :class="
        driverPortal.serviceDueCount ? 'border-accent-border-strong hover:border-accent-border' : 'border-border-subtle hover:border-accent-border'
      "
      @click="router.push('/driver/vehicles')"
    >
      <p class="text-xs text-foreground-muted">Service Due</p>
      <p class="mt-1 text-xl font-bold" :class="driverPortal.serviceDueCount ? 'text-accent' : 'text-foreground'">
        {{ driverPortal.serviceDueCount }}
      </p>
    </button>
    <button
      class="rounded-xl border p-4 text-left transition"
      :class="
        driverPortal.pendingBookingsCount
          ? 'border-accent-border-strong hover:border-accent-border'
          : 'border-border-subtle hover:border-accent-border'
      "
      @click="router.push('/driver/bookings')"
    >
      <p class="text-xs text-foreground-muted">Awaiting Approval</p>
      <p class="mt-1 text-xl font-bold" :class="driverPortal.pendingBookingsCount ? 'text-accent' : 'text-foreground'">
        {{ driverPortal.pendingBookingsCount }}
      </p>
    </button>
    <button
      class="rounded-xl border border-border-subtle bg-surface p-4 text-left transition hover:border-accent-border"
      @click="router.push('/driver/bookings')"
    >
      <p class="text-xs text-foreground-muted">Active Trips</p>
      <p class="mt-1 text-xl font-bold text-foreground">{{ driverPortal.activeTripsCount }}</p>
    </button>
    <button
      class="rounded-xl border border-border-subtle bg-surface p-4 text-left transition hover:border-accent-border"
      @click="router.push('/driver/bookings')"
    >
      <p class="text-xs text-foreground-muted">Completed Trips</p>
      <p class="mt-1 text-xl font-bold text-foreground">{{ driverPortal.completedTripsCount }}</p>
    </button>
  </div>
</template>
