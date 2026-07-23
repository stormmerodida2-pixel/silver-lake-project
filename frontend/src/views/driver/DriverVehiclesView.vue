<script setup>
import { ref } from 'vue'

import apiClient from '../../api/client'
import AddVehicleModal from '../../components/driver/AddVehicleModal.vue'
import { useDriverPortalStore } from '../../stores/driverPortal'

const driverPortal = useDriverPortalStore()

// ── Service history (per vehicle) ────────────────────────────────────────────
const serviceFormVehicleId = ref(null)
const serviceDateDraft = ref('')
const serviceNotesDraft = ref('')
const loggingServiceId = ref(null)
const serviceError = ref('')

function openServiceForm(vehicleId) {
  serviceFormVehicleId.value = vehicleId
  serviceDateDraft.value = new Date().toISOString().slice(0, 10)
  serviceNotesDraft.value = ''
  serviceError.value = ''
}

async function logService(vehicle) {
  if (!serviceDateDraft.value) return
  serviceError.value = ''
  loggingServiceId.value = vehicle.id
  try {
    const { data } = await apiClient.post('/driver/service-records/', {
      vehicle: vehicle.id,
      service_date: serviceDateDraft.value,
      notes: serviceNotesDraft.value.trim(),
    })
    driverPortal.addServiceRecord(vehicle.id, data)
    serviceFormVehicleId.value = null
  } catch (err) {
    const detail = err?.response?.data
    serviceError.value =
      typeof detail === 'object' ? Object.values(detail).flat().join(' ') : 'Could not log this service.'
  } finally {
    loggingServiceId.value = null
  }
}

// ── Add Vehicle modal ────────────────────────────────────────────────────────
const showAddVehicleModal = ref(false)
const addVehicleModal = ref(null)

async function openAddVehicleModal() {
  await addVehicleModal.value.open()
  showAddVehicleModal.value = true
}
</script>

<template>
  <div>
    <!-- My live vehicles -->
    <section>
      <h2 class="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gold-400">
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M5 17h14M6 17l1.5-5h9L18 17M9 12V8h6v4M10 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm5 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
          />
        </svg>
        My Vehicles
      </h2>
      <div class="mt-3 space-y-3">
        <div
          v-for="vehicle in driverPortal.profile.vehicles"
          :key="vehicle.id"
          class="rounded-xl border border-navy-800 bg-navy-900 p-4 transition hover:border-navy-700"
        >
          <div class="flex items-center gap-4">
            <div class="h-16 w-24 shrink-0 overflow-hidden rounded-lg border border-navy-800 bg-navy-800">
              <img v-if="vehicle.image" :src="vehicle.image" :alt="vehicle.name" class="h-full w-full object-cover" />
              <div v-else class="flex h-full w-full items-center justify-center text-slate-600">
                <svg class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 17h14M6 17l1.5-5h9L18 17M9 12V8h6v4" />
                </svg>
              </div>
            </div>
            <div class="flex-1">
              <p class="font-semibold text-white">{{ vehicle.name }}</p>
              <p class="text-xs text-slate-400">
                {{ vehicle.category_name || vehicle.category }} &middot; KES
                {{ Number(vehicle.price_per_day).toLocaleString() }}/day
              </p>
            </div>
            <span
              class="rounded-full px-2.5 py-0.5 text-xs font-semibold"
              :class="vehicle.is_available ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'"
            >
              {{ vehicle.is_available ? 'Available' : 'Unavailable' }}
            </span>
          </div>

          <p
            v-if="vehicle.is_service_due"
            class="mt-3 flex items-center gap-1.5 rounded-lg bg-gold-500/10 px-3 py-2 text-xs font-semibold text-gold-400"
          >
            <svg class="h-4 w-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
              />
            </svg>
            Service due - no service logged in the last 90 days. Log one below.
          </p>

          <!-- Service history -->
          <div class="mt-3 border-t border-navy-800 pt-3">
            <div class="flex items-center justify-between">
              <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Service History
                <span v-if="vehicle.service_records?.length" class="text-slate-600"
                  >({{ vehicle.service_records.length }})</span
                >
              </p>
              <button
                v-if="serviceFormVehicleId !== vehicle.id"
                class="text-xs font-semibold text-gold-400 hover:text-gold-300"
                @click="openServiceForm(vehicle.id)"
              >
                + Log Service
              </button>
              <button
                v-else
                class="text-xs font-semibold text-slate-400 hover:text-white"
                @click="serviceFormVehicleId = null"
              >
                Cancel
              </button>
            </div>

            <ul v-if="vehicle.service_records?.length" class="mt-2 space-y-1">
              <li v-for="record in vehicle.service_records" :key="record.id" class="text-xs text-slate-400">
                <span class="text-slate-300">{{ record.service_date }}</span>
                <span v-if="record.notes"> &middot; {{ record.notes }}</span>
              </li>
            </ul>
            <p v-else-if="serviceFormVehicleId !== vehicle.id" class="mt-2 text-xs text-slate-600">
              No service logged yet.
            </p>

            <form
              v-if="serviceFormVehicleId === vehicle.id"
              class="mt-2 space-y-2 rounded-lg bg-navy-950 p-3"
              @submit.prevent="logService(vehicle)"
            >
              <p v-if="serviceError" class="text-xs text-red-400">{{ serviceError }}</p>
              <div class="flex gap-2">
                <input
                  v-model="serviceDateDraft"
                  type="date"
                  required
                  class="rounded-md border border-navy-700 bg-navy-800 px-2 py-1.5 text-xs text-white focus:border-gold-500 focus:outline-none"
                />
                <input
                  v-model="serviceNotesDraft"
                  type="text"
                  placeholder="e.g. Oil change + filter"
                  class="flex-1 rounded-md border border-navy-700 bg-navy-800 px-2 py-1.5 text-xs text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                />
              </div>
              <button
                type="submit"
                :disabled="loggingServiceId === vehicle.id"
                class="rounded-md bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
              >
                {{ loggingServiceId === vehicle.id ? 'Saving...' : 'Save' }}
              </button>
            </form>
          </div>
        </div>
        <p v-if="!driverPortal.profile.vehicles.length" class="text-sm text-slate-500">No live vehicles yet.</p>
      </div>
    </section>

    <!-- Vehicle submissions -->
    <section class="mt-10">
      <div class="flex items-center justify-between">
        <h2 class="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gold-400">
          <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M4 6h16M4 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H6a2 2 0 01-2-2V6Z"
            />
          </svg>
          My Vehicle Submissions
        </h2>
        <button
          class="flex items-center gap-2 rounded-lg bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 transition hover:bg-gold-400"
          @click="openAddVehicleModal"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Add a Car
        </button>
      </div>
      <p class="mt-1 text-xs text-slate-500">New cars go live once an admin reviews and approves them.</p>

      <div class="mt-3 space-y-3">
        <div
          v-for="submission in driverPortal.profile.vehicle_submissions"
          :key="submission.id"
          class="rounded-xl border border-navy-800 bg-navy-900 p-4 transition hover:border-navy-700"
        >
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="font-semibold text-white">{{ submission.name }}</p>
              <p class="text-xs text-slate-400">
                {{ submission.category_name || submission.category }} &middot; KES
                {{ Number(submission.price_per_day).toLocaleString() }}/day
              </p>
            </div>
            <span
              class="rounded-full px-2.5 py-0.5 text-xs font-semibold"
              :class="{
                'bg-gold-500/10 text-gold-400': submission.status === 'pending',
                'bg-emerald-500/10 text-emerald-400': submission.status === 'approved',
                'bg-red-500/10 text-red-400': submission.status === 'rejected',
              }"
            >
              {{ submission.status }}
            </span>
          </div>
          <p v-if="submission.status === 'rejected' && submission.review_notes" class="mt-2 text-xs text-red-400">
            {{ submission.review_notes }}
          </p>
        </div>
        <p v-if="!driverPortal.profile.vehicle_submissions.length" class="text-sm text-slate-500">
          No submissions yet.
        </p>
      </div>
    </section>

    <AddVehicleModal ref="addVehicleModal" v-model="showAddVehicleModal" />
  </div>
</template>
