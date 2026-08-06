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
    class="flex flex-col items-center rounded-xl border border-border-subtle bg-surface p-6 text-center shadow-lg shadow-black/20"
  >
    <div class="h-24 w-24 overflow-hidden rounded-full bg-surface-2">
      <img v-if="driver.photo" :src="driver.photo" :alt="driver.full_name" class="h-full w-full object-cover" />
      <div v-else class="flex h-full items-center justify-center text-2xl font-bold text-foreground-muted">
        {{ driver.full_name.charAt(0) }}
      </div>
    </div>
    <h3 class="mt-4 font-[Georgia] text-lg font-bold text-foreground">{{ driver.full_name }}</h3>
    <p class="text-sm text-accent">{{ driver.years_of_experience }}+ years experience</p>
    <p class="mt-2 text-sm text-foreground-muted">{{ driver.bio }}</p>
    <p class="mt-3 text-sm font-semibold text-foreground">★ {{ Number(driver.rating).toFixed(1) }} / 5</p>
  </div>
</template>
