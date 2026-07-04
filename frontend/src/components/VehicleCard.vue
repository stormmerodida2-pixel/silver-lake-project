<script setup>
const props = defineProps({
  vehicle: {
    type: Object,
    required: true,
  },
})

const categoryLabels = {
  executive_suv: 'Executive SUV',
  premium_mpv: 'Premium MPV',
  compact_sedan: 'Compact Sedan',
  passenger_van: 'Passenger Van',
}
</script>

<template>
  <RouterLink
    :to="`/fleet/${vehicle.id}`"
    class="group flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg shadow-slate-200/60 transition hover:shadow-xl hover:-translate-y-0.5"
  >
    <div class="aspect-[4/3] w-full overflow-hidden bg-slate-100">
      <img
        v-if="vehicle.image"
        :src="vehicle.image"
        :alt="vehicle.name"
        class="h-full w-full object-cover transition duration-300 group-hover:scale-105"
      />
      <div v-else class="flex h-full items-center justify-center text-slate-400">No photo yet</div>
    </div>

    <div class="flex flex-1 flex-col gap-2 p-4">
      <h3 class="font-[Georgia] text-lg font-bold uppercase tracking-wide text-navy-900">
        {{ vehicle.name }}
      </h3>
      <p class="text-sm font-semibold text-brand-blue-600">
        {{ categoryLabels[vehicle.category] || vehicle.category }}
      </p>
      <p class="flex items-center gap-1 text-sm text-slate-600">
        {{ vehicle.passenger_capacity }} Passengers
      </p>
      <p v-if="vehicle.tagline" class="text-sm text-slate-500">{{ vehicle.tagline }}</p>

      <div class="mt-auto flex items-center justify-between pt-3">
        <span class="text-lg font-bold text-navy-900">
          KES {{ Number(vehicle.price_per_day).toLocaleString() }}<span class="text-sm font-normal text-slate-500">/day</span>
        </span>
        <span class="rounded-md bg-gold-500 px-3 py-1.5 text-sm font-semibold text-navy-950 transition group-hover:bg-gold-400">
          View Details
        </span>
      </div>
    </div>
  </RouterLink>
</template>
