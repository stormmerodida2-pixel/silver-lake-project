<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../api/client'
import VehicleCard from '../components/VehicleCard.vue'

const vehicles = ref([])
const loading = ref(true)
const error = ref('')

async function loadFavorites() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await apiClient.get('/vehicles/favorites/')
    vehicles.value = data
  } catch (err) {
    error.value = 'Could not load your favorites.'
  } finally {
    loading.value = false
  }
}

function removeFromList(vehicleId) {
  vehicles.value = vehicles.value.filter((v) => v.id !== vehicleId)
}

onMounted(loadFavorites)
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <h1 class="text-center font-[Georgia] text-3xl font-bold text-navy-900">My Favorites</h1>
      <p class="mt-2 text-center text-slate-600">Vehicles you've saved for later.</p>

      <p v-if="loading" class="mt-10 text-center text-slate-500">Loading...</p>
      <p v-else-if="error" class="mt-10 text-center text-red-600">{{ error }}</p>
      <p v-else-if="!vehicles.length" class="mt-10 text-center text-slate-500">
        No favorites yet - tap the heart on any vehicle to save it here.
        <RouterLink to="/fleet" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500">Browse the fleet</RouterLink>
      </p>

      <div v-else class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <VehicleCard
          v-for="vehicle in vehicles"
          :key="vehicle.id"
          :vehicle="vehicle"
          @unfavorited="removeFromList"
        />
      </div>
    </div>
  </div>
</template>
