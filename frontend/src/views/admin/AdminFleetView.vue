<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const { items: vehicles, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/fleet/')
const { items: driverOptions, load: loadDriverOptions } = useAdminList('/admin/drivers/')
const { items: fleetTypes, load: loadFleetTypes } = useAdminList('/admin/fleet-types/')
const busyId = ref(null)

// ── Shared Add / Edit modal ─────────────────────────────────────────────────
const showModal = ref(false)
const editingId = ref(null)   // null = create, number = edit
const editingVehicle = computed(() => vehicles.value.find((v) => v.id === editingId.value))
const saving = ref(false)
const formError = ref('')
const form = reactive({
  name: '',
  category: '',
  tagline: '',
  description: '',
  passenger_capacity: 4,
  price_per_day: '',
  allow_self_drive: true,
  allow_with_driver: true,
  is_available: true,
  driver: '',
  insurance_provider: '',
  insurance_policy_number: '',
  insurance_expiry_date: '',
  inspection_expiry_date: '',
})
const imageFile = ref(null)
const imagePreviewUrl = ref(null)

// ── Gallery photos (existing vehicles only) ─────────────────────────────────
const galleryImages = ref([])
const galleryUploading = ref(false)
const galleryError = ref('')
const removingImageId = ref(null)

async function addGalleryImages(event) {
  const files = Array.from(event.target.files || [])
  if (!files.length || !editingId.value) return
  galleryError.value = ''
  galleryUploading.value = true
  try {
    const payload = new FormData()
    files.forEach((file) => payload.append('images', file))
    const { data } = await apiClient.post(`/admin/fleet/${editingId.value}/gallery/`, payload)
    galleryImages.value.push(...data)
    syncGalleryToList()
  } catch (err) {
    galleryError.value = 'Could not upload one or more photos.'
  } finally {
    galleryUploading.value = false
    event.target.value = ''
  }
}

async function removeGalleryImage(image) {
  if (!editingId.value) return
  removingImageId.value = image.id
  try {
    await apiClient.delete(`/admin/fleet/${editingId.value}/gallery/${image.id}/`)
    galleryImages.value = galleryImages.value.filter((img) => img.id !== image.id)
    syncGalleryToList()
  } catch (err) {
    galleryError.value = 'Could not remove this photo.'
  } finally {
    removingImageId.value = null
  }
}

function syncGalleryToList() {
  const vehicle = vehicles.value.find((v) => v.id === editingId.value)
  if (vehicle) vehicle.gallery_images = [...galleryImages.value]
}

// ── Service history (existing vehicles only) ────────────────────────────────
const serviceRecords = ref([])
const serviceDateDraft = ref('')
const serviceNotesDraft = ref('')
const serviceSaving = ref(false)
const serviceError = ref('')

async function addServiceRecord() {
  if (!editingId.value || !serviceDateDraft.value) return
  serviceError.value = ''
  serviceSaving.value = true
  try {
    const { data } = await apiClient.post(`/admin/fleet/${editingId.value}/service-records/`, {
      service_date: serviceDateDraft.value,
      notes: serviceNotesDraft.value.trim(),
    })
    serviceRecords.value = [data, ...serviceRecords.value]
    syncServiceRecordsToList()
    serviceDateDraft.value = ''
    serviceNotesDraft.value = ''
  } catch (err) {
    serviceError.value = 'Could not log this service.'
  } finally {
    serviceSaving.value = false
  }
}

function syncServiceRecordsToList() {
  const vehicle = vehicles.value.find((v) => v.id === editingId.value)
  if (vehicle) vehicle.service_records = [...serviceRecords.value]
}

const modalTitle = () => editingId.value ? 'Edit Vehicle' : 'Add New Vehicle'
const submitLabel = () => saving.value
  ? (editingId.value ? 'Saving…' : 'Creating…')
  : (editingId.value ? 'Save Changes' : 'Add Vehicle')

function resetForm() {
  Object.assign(form, {
    name: '', category: fleetTypes.value.find((c) => c.is_active)?.slug || '', tagline: '', description: '',
    passenger_capacity: 4, price_per_day: '',
    allow_self_drive: true, allow_with_driver: true, is_available: true, driver: '',
    insurance_provider: '', insurance_policy_number: '',
    insurance_expiry_date: '', inspection_expiry_date: '',
  })
  imageFile.value = null
  imagePreviewUrl.value = null
  formError.value = ''
  galleryImages.value = []
  galleryError.value = ''
  serviceRecords.value = []
  serviceDateDraft.value = ''
  serviceNotesDraft.value = ''
  serviceError.value = ''
}

function openAddModal() {
  editingId.value = null
  resetForm()
  showModal.value = true
}

function openEditModal(vehicle) {
  editingId.value = vehicle.id
  galleryImages.value = vehicle.gallery_images ? [...vehicle.gallery_images] : []
  galleryError.value = ''
  serviceRecords.value = vehicle.service_records ? [...vehicle.service_records] : []
  serviceDateDraft.value = ''
  serviceNotesDraft.value = ''
  serviceError.value = ''
  Object.assign(form, {
    name: vehicle.name,
    category: vehicle.category,
    tagline: vehicle.tagline || '',
    description: vehicle.description || '',
    passenger_capacity: vehicle.passenger_capacity,
    price_per_day: vehicle.price_per_day,
    allow_self_drive: vehicle.allow_self_drive,
    allow_with_driver: vehicle.allow_with_driver,
    is_available: vehicle.is_available,
    driver: vehicle.driver || '',
    insurance_provider: vehicle.insurance_provider || '',
    insurance_policy_number: vehicle.insurance_policy_number || '',
    insurance_expiry_date: vehicle.insurance_expiry_date || '',
    inspection_expiry_date: vehicle.inspection_expiry_date || '',
  })
  imageFile.value = null
  imagePreviewUrl.value = vehicle.image || null
  formError.value = ''
  showModal.value = true
}

function onImageSelected(event) {
  const file = event.target.files[0]
  imageFile.value = file || null
  imagePreviewUrl.value = file ? URL.createObjectURL(file) : null
}

function buildPayload() {
  const payload = new FormData()
  payload.append('name', form.name)
  payload.append('category', form.category)
  payload.append('tagline', form.tagline)
  payload.append('description', form.description)
  payload.append('passenger_capacity', Number(form.passenger_capacity))
  payload.append('price_per_day', form.price_per_day)
  payload.append('allow_self_drive', form.allow_self_drive)
  payload.append('allow_with_driver', form.allow_with_driver)
  payload.append('is_available', form.is_available)
  payload.append('driver', form.driver)
  payload.append('insurance_provider', form.insurance_provider)
  payload.append('insurance_policy_number', form.insurance_policy_number)
  payload.append('insurance_expiry_date', form.insurance_expiry_date)
  payload.append('inspection_expiry_date', form.inspection_expiry_date)
  if (imageFile.value) payload.append('image', imageFile.value)
  return payload
}

async function saveVehicle() {
  formError.value = ''
  if (!form.name.trim() || !form.price_per_day) {
    formError.value = 'Name and price per day are required.'
    return
  }
  saving.value = true
  try {
    const payload = buildPayload()
    if (editingId.value) {
      const { data } = await apiClient.patch(`/admin/fleet/${editingId.value}/`, payload)
      const idx = vehicles.value.findIndex((v) => v.id === editingId.value)
      if (idx !== -1) vehicles.value[idx] = data
    } else {
      const { data } = await apiClient.post('/admin/fleet/', payload)
      vehicles.value.unshift(data)
    }
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    formError.value = typeof detail === 'object'
      ? Object.values(detail).flat().join(' ')
      : 'Could not save vehicle. Please try again.'
  } finally {
    saving.value = false
  }
}

async function toggleAvailability(vehicle) {
  busyId.value = vehicle.id
  try {
    const { data } = await apiClient.post(`/admin/fleet/${vehicle.id}/toggle-availability/`)
    Object.assign(vehicle, data)
  } catch {
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
    error.value = err.response?.data?.detail || 'Could not delete this vehicle.'
  } finally {
    busyId.value = null
  }
}

onMounted(() => {
  load()
  loadDriverOptions()
  loadFleetTypes()
})
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
        @click="openAddModal"
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
            <th class="px-4 py-3">Photo</th>
            <th class="px-4 py-3">Vehicle</th>
            <th class="px-4 py-3">Category</th>
            <th class="px-4 py-3">Capacity</th>
            <th class="px-4 py-3">Price/Day</th>
            <th class="px-4 py-3">Services</th>
            <th class="px-4 py-3">Maintenance</th>
            <th class="px-4 py-3">Insurance</th>
            <th class="px-4 py-3">Inspection</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-navy-800 bg-navy-950">
          <tr v-for="vehicle in vehicles" :key="vehicle.id">
            <td class="px-4 py-3">
              <div class="h-12 w-16 overflow-hidden rounded-md border border-navy-800 bg-navy-800">
                <img v-if="vehicle.image" :src="vehicle.image" :alt="vehicle.name" class="h-full w-full object-cover" />
                <div v-else class="flex h-full items-center justify-center text-xs text-slate-600">—</div>
              </div>
            </td>
            <td class="px-4 py-3">
              <p class="font-medium text-white">{{ vehicle.name }}</p>
              <p v-if="vehicle.tagline" class="text-xs text-slate-500">{{ vehicle.tagline }}</p>
              <p v-if="vehicle.driver_name" class="text-xs text-gold-400">Driver: {{ vehicle.driver_name }}</p>
            </td>
            <td class="px-4 py-3 text-slate-300">{{ vehicle.category_name || vehicle.category }}</td>
            <td class="px-4 py-3 text-slate-300">{{ vehicle.passenger_capacity }} pax</td>
            <td class="px-4 py-3 text-slate-300">KES {{ Number(vehicle.price_per_day).toLocaleString() }}</td>
            <td class="px-4 py-3 text-xs text-slate-400">
              <span v-if="vehicle.allow_self_drive" class="mr-1 rounded bg-navy-800 px-1.5 py-0.5">Self Drive</span>
              <span v-if="vehicle.allow_with_driver" class="rounded bg-navy-800 px-1.5 py-0.5">With Driver</span>
            </td>
            <td class="px-4 py-3">
              <span v-if="vehicle.is_service_due" class="text-xs font-bold text-gold-400">⚠ Due</span>
              <span v-else class="text-xs text-slate-500">Up to date</span>
            </td>
            <td class="px-4 py-3">
              <span v-if="vehicle.insurance_expiry_date"
                :class="vehicle.is_insurance_expired ? 'text-red-400' : 'text-slate-400'" class="text-xs">
                {{ vehicle.insurance_expiry_date }}
                <span v-if="vehicle.is_insurance_expired" class="ml-1 font-bold">⚠ Expired</span>
              </span>
              <span v-else class="text-xs text-slate-600">—</span>
            </td>
            <td class="px-4 py-3">
              <span v-if="vehicle.inspection_expiry_date"
                :class="vehicle.is_inspection_expired ? 'text-red-400' : 'text-slate-400'" class="text-xs">
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
                v-if="auth.user?.is_superuser"
                :disabled="busyId === vehicle.id"
                class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="openEditModal(vehicle)"
              >
                Edit
              </button>
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

    <!-- Add / Edit Vehicle Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-2xl rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">{{ modalTitle() }}</h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ formError }}</p>

            <form class="space-y-5" @submit.prevent="saveVehicle">

              <!-- Basic info -->
              <div class="grid grid-cols-2 gap-4">
                <div class="col-span-2">
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Vehicle Name *</label>
                  <input
                    v-model="form.name" type="text" placeholder="Toyota Prado TZG" required
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Category</label>
                  <select v-model="form.category"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none">
                    <option v-for="cat in fleetTypes" :key="cat.slug" :value="cat.slug">
                      {{ cat.name }}{{ cat.is_active ? '' : ' (Inactive)' }}
                    </option>
                  </select>
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Capacity (pax) *</label>
                  <input v-model="form.passenger_capacity" type="number" min="1" max="50"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Price / Day (KES) *</label>
                  <input v-model="form.price_per_day" type="number" min="0" step="0.01" placeholder="15000" required
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Tagline</label>
                  <input v-model="form.tagline" type="text" placeholder="Luxury · Power · Prestige"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div class="col-span-2">
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Description</label>
                  <textarea v-model="form.description" rows="3"
                    placeholder="Full vehicle description shown on the detail page..."
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  ></textarea>
                </div>
              </div>

              <!-- Photo -->
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Vehicle Photo</label>
                <div class="flex items-center gap-3">
                  <div class="h-16 w-24 shrink-0 overflow-hidden rounded-lg border border-navy-700 bg-navy-800">
                    <img v-if="imagePreviewUrl" :src="imagePreviewUrl" alt="Preview" class="h-full w-full object-cover" />
                    <div v-else class="flex h-full items-center justify-center text-xs text-slate-500">No photo</div>
                  </div>
                  <input type="file" accept="image/*"
                    class="w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
                    @change="onImageSelected"
                  />
                </div>
                <p v-if="editingId" class="mt-1 text-xs text-slate-500">Leave blank to keep the existing photo.</p>
              </div>

              <!-- Gallery photos (existing vehicles only) -->
              <div v-if="editingId">
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">
                  Gallery Photos
                </label>
                <p v-if="galleryError" class="mb-2 text-xs text-red-400">{{ galleryError }}</p>
                <div class="flex flex-wrap gap-2">
                  <div
                    v-for="image in galleryImages"
                    :key="image.id"
                    class="group relative h-16 w-24 shrink-0 overflow-hidden rounded-lg border border-navy-700 bg-navy-800"
                  >
                    <img :src="image.image" alt="Gallery photo" class="h-full w-full object-cover" />
                    <button
                      type="button"
                      :disabled="removingImageId === image.id"
                      class="absolute inset-0 flex items-center justify-center bg-black/60 text-xs font-semibold text-white opacity-0 transition group-hover:opacity-100 disabled:opacity-100"
                      @click="removeGalleryImage(image)"
                    >
                      {{ removingImageId === image.id ? 'Removing…' : 'Remove' }}
                    </button>
                  </div>
                </div>
                <input type="file" accept="image/*" multiple :disabled="galleryUploading"
                  class="mt-2 w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950 disabled:opacity-50"
                  @change="addGalleryImages"
                />
                <p class="mt-1 text-xs text-slate-500">
                  {{ galleryUploading ? 'Uploading…' : 'Uploads immediately, separate from the fields below.' }}
                </p>
              </div>

              <!-- Service history (existing vehicles only) -->
              <div v-if="editingId">
                <label class="mb-1 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                  Service History
                  <span v-if="editingVehicle?.is_service_due" class="rounded-full bg-gold-500/10 px-2 py-0.5 text-[10px] font-bold normal-case tracking-normal text-gold-400">
                    ⚠ Due (90+ days)
                  </span>
                </label>
                <p v-if="serviceError" class="mb-2 text-xs text-red-400">{{ serviceError }}</p>
                <ul v-if="serviceRecords.length" class="mb-2 space-y-1 rounded-lg border border-navy-700 p-3">
                  <li v-for="record in serviceRecords" :key="record.id" class="text-xs text-slate-300">
                    <span class="text-white">{{ record.service_date }}</span>
                    <span v-if="record.notes" class="text-slate-400"> &middot; {{ record.notes }}</span>
                    <span v-if="record.logged_by_name" class="text-slate-500"> (logged by {{ record.logged_by_name }})</span>
                  </li>
                </ul>
                <p v-else class="mb-2 text-xs text-slate-500">No service logged yet.</p>
                <div v-if="auth.user?.is_superuser" class="flex gap-2">
                  <input
                    v-model="serviceDateDraft" type="date"
                    class="rounded-lg border border-navy-700 bg-navy-800 px-3 py-2 text-sm text-white focus:border-gold-500 focus:outline-none"
                  />
                  <input
                    v-model="serviceNotesDraft" type="text" placeholder="e.g. Oil change + filter"
                    class="flex-1 rounded-lg border border-navy-700 bg-navy-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    :disabled="serviceSaving || !serviceDateDraft"
                    class="shrink-0 rounded-lg bg-gold-500 px-3 py-2 text-sm font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                    @click="addServiceRecord"
                  >
                    {{ serviceSaving ? 'Saving…' : 'Log' }}
                  </button>
                </div>
                <p class="mt-1 text-xs text-slate-500">Logs immediately, separate from the fields below.</p>
              </div>

              <!-- Insurance & Inspection -->
              <div class="grid grid-cols-2 gap-4 rounded-xl border border-navy-700 p-4">
                <p class="col-span-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Insurance &amp; Inspection</p>
                <div>
                  <label class="mb-1 block text-xs text-slate-400">Insurance Provider</label>
                  <input v-model="form.insurance_provider" type="text" placeholder="Jubilee Insurance"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs text-slate-400">Policy Number</label>
                  <input v-model="form.insurance_policy_number" type="text" placeholder="POL-00123"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs text-slate-400">Insurance Expiry</label>
                  <input v-model="form.insurance_expiry_date" type="date"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-3 py-2 text-sm text-white focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs text-slate-400">Inspection Expiry</label>
                  <input v-model="form.inspection_expiry_date" type="date"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-3 py-2 text-sm text-white focus:border-gold-500 focus:outline-none"
                  />
                </div>
              </div>

              <!-- Driver assignment -->
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Assigned Driver</label>
                <select v-model="form.driver"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none">
                  <option value="">No driver assigned</option>
                  <option v-for="d in driverOptions" :key="d.id" :value="d.id">{{ d.full_name }}</option>
                </select>
                <p class="mt-1 text-xs text-slate-500">
                  Who drives this vehicle on "with driver" bookings. Only needed for company-owned
                  vehicles — a driver-partner's own submitted car is assigned automatically.
                </p>
              </div>

              <!-- Checkboxes -->
              <div class="flex flex-wrap gap-4">
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
                <button type="button"
                  class="flex-1 rounded-lg border border-navy-700 py-2.5 text-sm font-semibold text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
                  @click="showModal = false">
                  Cancel
                </button>
                <button type="submit" :disabled="saving"
                  class="flex-1 rounded-lg bg-gold-500 py-2.5 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400 disabled:opacity-50">
                  {{ submitLabel() }}
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
