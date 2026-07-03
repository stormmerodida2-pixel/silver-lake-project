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
  <div class="flex flex-col overflow-hidden rounded-xl border border-navy-800 bg-navy-900 shadow-lg shadow-black/20">
    <div class="aspect-4/3 w-full bg-navy-800">
      <img
        v-if="vehicle.image"
        :src="vehicle.image"
        :alt="vehicle.name"
        class="h-full w-full object-cover"
      />
      <div v-else class="flex h-full items-center justify-center text-slate-500">No photo yet</div>
    </div>

    <div class="flex flex-1 flex-col gap-2 p-4">
      <h3 class="font-[Georgia] text-lg font-bold uppercase tracking-wide text-white">
        {{ vehicle.name }}
      </h3>
      <p class="text-sm font-semibold text-gold-400">
        {{ categoryLabels[vehicle.category] || vehicle.category }}
      </p>
      <p class="flex items-center gap-1 text-sm text-slate-300">
        {{ vehicle.passenger_capacity }} Passengers
      </p>
      <p v-if="vehicle.tagline" class="text-sm text-slate-400">{{ vehicle.tagline }}</p>

      <div class="mt-auto flex items-center justify-between pt-3">
        <span class="text-lg font-bold text-white">
          KES {{ Number(vehicle.price_per_day).toLocaleString() }}<span class="text-sm font-normal text-slate-400">/day</span>
        </span>
        <RouterLink
          :to="`/book?vehicle=${vehicle.id}`"
          class="rounded-md bg-gold-500 px-3 py-1.5 text-sm font-semibold text-navy-950 transition hover:bg-gold-400"
        >
          Book This
        </RouterLink>
      </div>
    </div>
  </div>
</template>
