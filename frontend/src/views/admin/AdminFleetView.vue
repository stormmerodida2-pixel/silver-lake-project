<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const { items: vehicles, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/fleet/')
const busyId = ref(null)

const categoryLabels = {
  executive_suv: 'Executive SUV',
  premium_mpv: 'Premium MPV',
  compact_sedan: 'Compact Sedan',
  passenger_van: 'Passenger Van',
}

// ── Add Vehicle modal ───────────────────────────────────────────────────────
const showModal = ref(false)
const saving = ref(false)
const formError = ref('')
const form = reactive({
  name: '',
  category: 'executive_suv',
  tagline: '',
  passenger_capacity: 4,
  price_per_day: '',
  allow_self_drive: true,
  allow_with_driver: true,
  is_available: true,
})

function openModal() {
  Object.assign(form, {
    name: '', category: 'executive_suv', tagline: '',
    passenger_capacity: 4, price_per_day: '',
    allow_self_drive: true, allow_with_driver: true, is_available: true,
  })
  formError.value = ''
  showModal.value = true
}

async function createVehicle() {
  formError.value = ''
  if (!form.name.trim() || !form.price_per_day) {
    formError.value = 'Name and price per day are required.'
    return
  }
  saving.value = true
  try {
    const { data } = await apiClient.post('/admin/fleet/', {
      name: form.name,
      category: form.category,
      tagline: form.tagline,
      passenger_capacity: Number(form.passenger_capacity),
      price_per_day: form.price_per_day,
      allow_self_drive: form.allow_self_drive,
      allow_with_driver: form.allow_with_driver,
      is_available: form.is_available,
    })
    vehicles.value.unshift(data)
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    if (typeof detail === 'object') {
      formError.value = Object.values(detail).flat().join(' ')
    } else {
      formError.value = 'Could not create vehicle. Please try again.'
    }
  } finally {
    saving.value = false
  }
}

async function toggleAvailability(vehicle) {
  busyId.value = vehicle.id
  try {
    const { data } = await apiClient.post(`/admin/fleet/${vehicle.id}/toggle-availability/`)
    Object.assign(vehicle, data)
  } catch (err) {
    error.value = 'Could not update vehicle.'
  } finally {
    busyId.value = null
  }
}

async function deleteVehicle(vehicle) {
  if (!confirm(`Delete "${vehicle.name}"? This cannot be undone.`)) return
  busyId.value = vehicle.id
  try {
    await apiClient.delete(`/admin/fleet/${vehicle.id}/`)
    vehicles.value = vehicles.value.filter((v) => v.id !== vehicle.id)
  } catch (err) {
    error.value = 'Could not delete this vehicle.'
  } finally {
    busyId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h1 class="font-[Georgia] text-2xl font-bold text-white">Manage Fleet</h1>
      <button
        v-if="auth.user?.is_superuser"
        id="add-vehicle-btn"
        class="flex items-center gap-2 rounded-lg bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400"
        @click="openModal"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        Add Vehicle
      </button>
    </div>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <div v-if="!loading" class="mt-6 overflow-x-auto rounded-xl border border-navy-800">
      <table class="w-full text-left text-sm">
        <thead class="bg-navy-900 text-slate-400">
          <tr>
            <th class="px-4 py-3">Vehicle</th>
            <th class="px-4 py-3">Category</th>
            <th class="px-4 py-3">Capacity</th>
            <th class="px-4 py-3">Price/Day</th>
            <th class="px-4 py-3">Services</th>
            <th class="px-4 py-3">Insurance</th>
            <th class="px-4 py-3">Inspection</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-navy-800 bg-navy-950">
          <tr v-for="vehicle in vehicles" :key="vehicle.id">
            <td class="px-4 py-3">
              <p class="font-medium text-white">{{ vehicle.name }}</p>
              <p v-if="vehicle.tagline" class="text-xs text-slate-500">{{ vehicle.tagline }}</p>
            </td>
            <td class="px-4 py-3 text-slate-300">{{ categoryLabels[vehicle.category] || vehicle.category }}</td>
            <td class="px-4 py-3 text-slate-300">{{ vehicle.passenger_capacity }} pax</td>
            <td class="px-4 py-3 text-slate-300">KES {{ Number(vehicle.price_per_day).toLocaleString() }}</td>
            <td class="px-4 py-3 text-xs text-slate-400">
              <span v-if="vehicle.allow_self_drive" class="mr-1 rounded bg-navy-800 px-1.5 py-0.5">Self Drive</span>
              <span v-if="vehicle.allow_with_driver" class="rounded bg-navy-800 px-1.5 py-0.5">With Driver</span>
            </td>
            <td class="px-4 py-3">
              <span v-if="vehicle.insurance_expiry_date" :class="vehicle.is_insurance_expired ? 'text-red-400' : 'text-slate-400'" class="text-xs">
                {{ vehicle.insurance_expiry_date }}
                <span v-if="vehicle.is_insurance_expired" class="ml-1 font-bold">⚠ Expired</span>
              </span>
              <span v-else class="text-xs text-slate-600">—</span>
            </td>
            <td class="px-4 py-3">
              <span v-if="vehicle.inspection_expiry_date" :class="vehicle.is_inspection_expired ? 'text-red-400' : 'text-slate-400'" class="text-xs">
                {{ vehicle.inspection_expiry_date }}
                <span v-if="vehicle.is_inspection_expired" class="ml-1 font-bold">⚠ Expired</span>
              </span>
              <span v-else class="text-xs text-slate-600">—</span>
            </td>
            <td class="px-4 py-3">
              <span :class="vehicle.is_available ? 'text-gold-400' : 'text-red-400'">
                {{ vehicle.is_available ? 'Available' : 'Unavailable' }}
              </span>
            </td>
            <td class="space-x-2 whitespace-nowrap px-4 py-3">
              <button
                :disabled="busyId === vehicle.id"
                class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="toggleAvailability(vehicle)"
              >
                {{ vehicle.is_available ? 'Disable' : 'Enable' }}
              </button>
              <button
                v-if="auth.user?.is_superuser"
                :disabled="busyId === vehicle.id"
                class="rounded-md border border-red-400 px-2 py-1 text-xs font-semibold text-red-400 hover:bg-red-400 hover:text-navy-950 disabled:opacity-50"
                @click="deleteVehicle(vehicle)"
              >
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!vehicles.length" class="p-6 text-center text-slate-400">No vehicles in the fleet yet.</p>
      <div v-if="nextUrl" class="border-t border-navy-800 p-3 text-center">
        <button
          :disabled="loadingMore"
          class="rounded-md border border-navy-700 px-4 py-1.5 text-sm font-medium text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
          @click="loadMore"
        >
          {{ loadingMore ? 'Loading...' : 'Load More' }}
        </button>
      </div>
    </div>

    <!-- Add Vehicle Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showModal"
          id="add-vehicle-modal"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-lg rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">Add New Vehicle</h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ formError }}</p>

            <form class="space-y-4" @submit.prevent="createVehicle">
              <div class="grid grid-cols-2 gap-4">
                <div class="col-span-2">
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Vehicle Name *</label>
                  <input
                    id="new-vehicle-name"
                    v-model="form.name"
                    type="text"
                    placeholder="Toyota Prado TZG"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                    required
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Category</label>
                  <select
                    id="new-vehicle-category"
                    v-model="form.category"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                  >
                    <option v-for="(label, val) in categoryLabels" :key="val" :value="val">{{ label }}</option>
                  </select>
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Capacity (pax) *</label>
                  <input
                    id="new-vehicle-capacity"
                    v-model="form.passenger_capacity"
                    type="number"
                    min="1"
                    max="50"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Price / Day (KES) *</label>
                  <input
                    id="new-vehicle-price"
                    v-model="form.price_per_day"
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="15000"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                    required
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Tagline</label>
                  <input
                    id="new-vehicle-tagline"
                    v-model="form.tagline"
                    type="text"
                    placeholder="Luxury · Power · Prestige"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                </div>
              </div>

              <div class="flex flex-wrap gap-4 pt-1">
                <label class="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
                  <input v-model="form.allow_self_drive" type="checkbox" class="accent-gold-500" />
                  Allow Self Drive
                </label>
                <label class="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
                  <input v-model="form.allow_with_driver" type="checkbox" class="accent-gold-500" />
                  Allow With Driver
                </label>
                <label class="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
                  <input v-model="form.is_available" type="checkbox" class="accent-gold-500" />
                  Mark as Available
                </label>
              </div>

              <div class="flex gap-3 pt-2">
                <button
                  type="button"
                  class="flex-1 rounded-lg border border-navy-700 py-2.5 text-sm font-semibold text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
                  @click="showModal = false"
                >
                  Cancel
                </button>
                <button
                  id="create-vehicle-submit"
                  type="submit"
                  :disabled="saving"
                  class="flex-1 rounded-lg bg-gold-500 py-2.5 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400 disabled:opacity-50"
                >
                  {{ saving ? 'Creating…' : 'Add Vehicle' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active { transition: opacity 0.2s ease; }
.modal-fade-enter-from,
.modal-fade-leave-to { opacity: 0; }
</style>
