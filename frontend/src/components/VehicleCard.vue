<script setup>
const props = defineProps({
  vehicle: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <RouterLink
    :to="`/fleet/${vehicle.id}`"
    class="group flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg shadow-slate-200/60 transition-all duration-300 ease-out hover:-translate-y-1 hover:border-gold-300 hover:shadow-xl hover:shadow-gold-500/10"
  >
    <div class="relative aspect-[4/3] w-full overflow-hidden bg-slate-100">
      <img
        v-if="vehicle.image"
        :src="vehicle.image"
        :alt="vehicle.name"
        class="h-full w-full object-cover transition-transform duration-500 ease-out group-hover:scale-110"
      />
      <div v-else class="flex h-full items-center justify-center text-slate-400">No photo yet</div>

      <!-- Real social proof - a genuine completed-trip count, never a fabricated "X viewing now". -->
      <span
        v-if="vehicle.trips_completed > 0"
        class="absolute right-3 top-3 rounded-full bg-navy-950/80 px-2.5 py-1 text-xs font-semibold text-gold-400 backdrop-blur"
      >
        {{ vehicle.trips_completed }} trip{{ vehicle.trips_completed === 1 ? '' : 's' }} completed
      </span>
    </div>

    <div class="flex flex-1 flex-col gap-2 p-4">
      <h3 class="font-[Georgia] text-lg font-bold uppercase tracking-wide text-navy-900">
        {{ vehicle.name }}
      </h3>
      <p class="text-sm font-semibold text-brand-blue-600">
        {{ vehicle.category_name || vehicle.category }}
      </p>
      <p class="flex items-center gap-1 text-sm text-slate-600">
        {{ vehicle.passenger_capacity }} Passengers
      </p>
      <p v-if="vehicle.tagline" class="text-sm text-slate-500">{{ vehicle.tagline }}</p>

      <div class="mt-auto flex items-center justify-between pt-3">
        <span class="text-lg font-bold text-navy-900">
          KES {{ Number(vehicle.price_per_day).toLocaleString() }}<span class="text-sm font-normal text-slate-500">/day</span>
        </span>
        <span class="flex items-center gap-1 rounded-md bg-gold-500 px-3 py-1.5 text-sm font-semibold text-navy-950 transition-colors group-hover:bg-gold-400">
          View Details
          <svg class="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-0.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </span>
      </div>
    </div>
  </RouterLink>
</template>
