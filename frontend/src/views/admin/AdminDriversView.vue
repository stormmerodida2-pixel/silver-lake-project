<script setup>
import { computed, onMounted, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'

const {
  items: drivers,
  nextUrl: driversNextUrl,
  loading: driversLoading,
  loadingMore: driversLoadingMore,
  error: driversError,
  load: loadDrivers,
  loadMore: loadMoreDrivers,
} = useAdminList('/admin/drivers/')

const {
  items: applications,
  nextUrl: applicationsNextUrl,
  loading: applicationsLoading,
  loadingMore: applicationsLoadingMore,
  error: applicationsError,
  load: loadApplications,
  loadMore: loadMoreApplications,
} = useAdminList('/admin/driver-applications/')

const busyId = ref(null)
const loading = computed(() => driversLoading.value || applicationsLoading.value)
const error = computed(() => driversError.value || applicationsError.value)

const pendingApplications = computed(() => applications.value.filter((a) => a.status === 'pending'))
const reviewedApplications = computed(() => applications.value.filter((a) => a.status !== 'pending'))

async function toggleDriverActive(driver) {
  busyId.value = driver.id
  try {
    const action = driver.is_active ? 'suspend' : 'activate'
    const { data } = await apiClient.post(`/admin/drivers/${driver.id}/${action}/`)
    Object.assign(driver, data)
  } catch (err) {
    driversError.value = 'Could not update this driver.'
  } finally {
    busyId.value = null
  }
}

async function deleteDriver(driver) {
  if (!confirm(`Delete ${driver.full_name}? This cannot be undone.`)) return
  busyId.value = driver.id
  try {
    await apiClient.delete(`/admin/drivers/${driver.id}/`)
    drivers.value = drivers.value.filter((d) => d.id !== driver.id)
  } catch (err) {
    driversError.value = 'Could not delete this driver.'
  } finally {
    busyId.value = null
  }
}

async function approveApplication(application) {
  busyId.value = application.id
  try {
    const { data } = await apiClient.post(`/admin/driver-applications/${application.id}/approve/`)
    Object.assign(application, data)
    await loadDrivers()
  } catch (err) {
    applicationsError.value = 'Could not approve this application.'
  } finally {
    busyId.value = null
  }
}

async function rejectApplication(application) {
  busyId.value = application.id
  try {
    const { data } = await apiClient.post(`/admin/driver-applications/${application.id}/reject/`)
    Object.assign(application, data)
  } catch (err) {
    applicationsError.value = 'Could not reject this application.'
  } finally {
    busyId.value = null
  }
}

onMounted(() => {
  loadDrivers()
  loadApplications()
})
</script>

<template>
  <div>
    <h1 class="font-[Georgia] text-2xl font-bold text-white">Manage Drivers</h1>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <template v-if="!loading">
      <section class="mt-8">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">
          Pending Applications ({{ pendingApplications.length }})
        </h2>
        <div class="mt-3 space-y-4">
          <div
            v-for="application in pendingApplications"
            :key="application.id"
            class="rounded-xl border border-gold-500 bg-navy-900 p-5"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 class="font-[Georgia] text-lg font-bold text-white">{{ application.full_name }}</h3>
                <p class="text-sm text-slate-400">{{ application.email }} - {{ application.phone_number }}</p>
                <p class="text-sm text-slate-400">
                  {{ application.years_of_experience }} years experience - License #{{ application.license_number }}
                </p>
                <p class="mt-1 text-sm text-slate-300">
                  Vehicle: {{ application.vehicle_name }} ({{ application.vehicle_category }}),
                  {{ application.passenger_capacity }} pax, KES {{ Number(application.price_per_day).toLocaleString() }}/day
                </p>
                <div class="mt-2 flex flex-wrap gap-3 text-sm">
                  <a :href="application.license_document" target="_blank" class="text-gold-400 hover:text-gold-300">
                    License Document
                  </a>
                  <a
                    v-if="application.vehicle_photo"
                    :href="application.vehicle_photo"
                    target="_blank"
                    class="text-gold-400 hover:text-gold-300"
                  >
                    Vehicle Photo
                  </a>
                  <a
                    v-if="application.vehicle_logbook_document"
                    :href="application.vehicle_logbook_document"
                    target="_blank"
                    class="text-gold-400 hover:text-gold-300"
                  >
                    Logbook
                  </a>
                </div>
              </div>
              <div class="flex gap-2">
                <button
                  :disabled="busyId === application.id"
                  class="rounded-md bg-gold-500 px-3 py-1.5 text-sm font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                  @click="approveApplication(application)"
                >
                  Approve
                </button>
                <button
                  :disabled="busyId === application.id"
                  class="rounded-md border border-red-400 px-3 py-1.5 text-sm font-semibold text-red-400 hover:bg-red-400 hover:text-navy-950 disabled:opacity-50"
                  @click="rejectApplication(application)"
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
          <p v-if="!pendingApplications.length" class="text-sm text-slate-400">No pending applications.</p>
          <div v-if="applicationsNextUrl" class="text-center">
            <button
              :disabled="applicationsLoadingMore"
              class="rounded-md border border-navy-700 px-4 py-1.5 text-sm font-medium text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
              @click="loadMoreApplications"
            >
              {{ applicationsLoadingMore ? 'Loading...' : 'Load More Applications' }}
            </button>
          </div>
        </div>
      </section>

      <section class="mt-10">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Live Drivers</h2>
        <div class="mt-3 overflow-x-auto rounded-xl border border-navy-800">
          <table class="w-full text-left text-sm">
            <thead class="bg-navy-900 text-slate-400">
              <tr>
                <th class="px-4 py-3">Name</th>
                <th class="px-4 py-3">Phone</th>
                <th class="px-4 py-3">Experience</th>
                <th class="px-4 py-3">Rating</th>
                <th class="px-4 py-3">Status</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-navy-800 bg-navy-950">
              <tr v-for="driver in drivers" :key="driver.id">
                <td class="px-4 py-3 text-white">{{ driver.full_name }}</td>
                <td class="px-4 py-3 text-slate-300">{{ driver.phone_number || '-' }}</td>
                <td class="px-4 py-3 text-slate-300">{{ driver.years_of_experience }} yrs</td>
                <td class="px-4 py-3 text-slate-300">{{ Number(driver.rating).toFixed(1) }}</td>
                <td class="px-4 py-3">
                  <span :class="driver.is_active ? 'text-gold-400' : 'text-red-400'">
                    {{ driver.is_active ? 'Active' : 'Suspended' }}
                  </span>
                </td>
                <td class="space-x-2 whitespace-nowrap px-4 py-3">
                  <button
                    :disabled="busyId === driver.id"
                    class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                    @click="toggleDriverActive(driver)"
                  >
                    {{ driver.is_active ? 'Suspend' : 'Activate' }}
                  </button>
                  <button
                    :disabled="busyId === driver.id"
                    class="rounded-md border border-red-400 px-2 py-1 text-xs font-semibold text-red-400 hover:bg-red-400 hover:text-navy-950 disabled:opacity-50"
                    @click="deleteDriver(driver)"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-if="!drivers.length" class="p-6 text-center text-slate-400">No drivers yet.</p>
          <div v-if="driversNextUrl" class="border-t border-navy-800 p-3 text-center">
            <button
              :disabled="driversLoadingMore"
              class="rounded-md border border-navy-700 px-4 py-1.5 text-sm font-medium text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
              @click="loadMoreDrivers"
            >
              {{ driversLoadingMore ? 'Loading...' : 'Load More' }}
            </button>
          </div>
        </div>
      </section>

      <section v-if="reviewedApplications.length" class="mt-10">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-gold-400">Reviewed Applications</h2>
        <div class="mt-3 space-y-2">
          <div
            v-for="application in reviewedApplications"
            :key="application.id"
            class="flex items-center justify-between rounded-md border border-navy-800 bg-navy-900 px-4 py-2 text-sm"
          >
            <span class="text-slate-300">{{ application.full_name }} - {{ application.vehicle_name }}</span>
            <span :class="application.status === 'approved' ? 'text-gold-400' : 'text-red-400'">
              {{ application.status }}
            </span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
