<script setup>
defineProps({
  driver: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <div
    class="flex flex-col items-center rounded-xl border border-slate-200 bg-white p-6 text-center shadow-lg shadow-slate-200/60"
  >
    <div class="h-24 w-24 overflow-hidden rounded-full bg-slate-100">
      <img v-if="driver.photo" :src="driver.photo" :alt="driver.full_name" class="h-full w-full object-cover" />
      <div v-else class="flex h-full items-center justify-center text-2xl font-bold text-slate-400">
        {{ driver.full_name.charAt(0) }}
      </div>
    </div>
    <h3 class="mt-4 font-[Georgia] text-lg font-bold text-navy-900">{{ driver.full_name }}</h3>
    <p class="text-sm text-brand-blue-600">{{ driver.years_of_experience }}+ years experience</p>
    <p class="mt-2 text-sm text-slate-600">{{ driver.bio }}</p>
    <p class="mt-3 text-sm font-semibold text-navy-900">★ {{ Number(driver.rating).toFixed(1) }} / 5</p>
  </div>
</template>
