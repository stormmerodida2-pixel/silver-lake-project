<script setup>
import { onMounted } from 'vue'

import { useCatalogStore } from '../stores/catalog'
import DriverCard from '../components/DriverCard.vue'

const catalog = useCatalogStore()

onMounted(() => {
  catalog.fetchDrivers()
})
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
    <h1 class="text-center font-[Georgia] text-3xl font-bold text-white">Meet Our Drivers</h1>
    <p class="mt-2 text-center text-slate-400">Professional, friendly chauffeurs who treat you like family.</p>

    <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
      <DriverCard v-for="driver in catalog.drivers" :key="driver.id" :driver="driver" />
    </div>

    <p v-if="!catalog.drivers.length" class="mt-10 text-center text-slate-400">No drivers listed yet.</p>
  </div>
</template>
