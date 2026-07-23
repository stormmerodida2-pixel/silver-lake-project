<script setup>
import { reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useCatalogStore } from '../../stores/catalog'
import { useDriverPortalStore } from '../../stores/driverPortal'

defineProps({
  modelValue: { type: Boolean, required: true },
})
const emit = defineEmits(['update:modelValue'])

const catalog = useCatalogStore()
const driverPortal = useDriverPortalStore()

const saving = ref(false)
const formError = ref('')
const form = reactive({
  name: '',
  category: '',
  tagline: '',
  description: '',
  passenger_capacity: 4,
  price_per_day: '',
})
const photoFiles = ref([])
const photoPreviewUrls = ref([])
const logbookFile = ref(null)

function close() {
  emit('update:modelValue', false)
}

async function open() {
  await catalog.fetchCategories()
  Object.assign(form, {
    name: '',
    category: catalog.categories[0]?.slug || '',
    tagline: '',
    description: '',
    passenger_capacity: 4,
    price_per_day: '',
  })
  photoFiles.value = []
  photoPreviewUrls.value = []
  logbookFile.value = null
  formError.value = ''
}

defineExpose({ open })

function onPhotosSelected(event) {
  // Adds to whatever's already picked, rather than replacing it - a file input's own .files
  // list is wiped clean on every selection, so picking one photo, then going back to add
  // another separately, would otherwise silently drop the first one instead of accumulating.
  photoFiles.value = [...photoFiles.value, ...Array.from(event.target.files)]
  photoPreviewUrls.value = photoFiles.value.map((file) => URL.createObjectURL(file))
  event.target.value = ''
}

function removePhoto(index) {
  photoFiles.value = photoFiles.value.filter((_, i) => i !== index)
  photoPreviewUrls.value = photoPreviewUrls.value.filter((_, i) => i !== index)
}

async function submitVehicle() {
  formError.value = ''
  if (!form.name.trim() || !form.price_per_day || !logbookFile.value) {
    formError.value = 'Vehicle name, price per day, and logbook document are required.'
    return
  }
  if (photoFiles.value.length < 2) {
    formError.value = 'Please add at least 2 photos of the vehicle.'
    return
  }
  saving.value = true
  try {
    const payload = new FormData()
    Object.entries(form).forEach(([key, value]) => payload.append(key, value))
    photoFiles.value.forEach((file) => payload.append('images', file))
    payload.append('logbook_document', logbookFile.value)

    const { data } = await apiClient.post('/driver/vehicle-submissions/', payload)
    driverPortal.addVehicleSubmission(data)
    close()
  } catch (err) {
    const detail = err?.response?.data
    formError.value =
      typeof detail === 'object'
        ? Object.values(detail).flat().join(' ')
        : 'Could not submit this vehicle. Please try again.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        v-if="modelValue"
        class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
        @click.self="close"
      >
        <div class="w-full max-w-lg rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
          <div class="mb-6 flex items-center justify-between">
            <h2 class="font-[Georgia] text-xl font-bold text-white">Add a Car</h2>
            <button class="text-slate-400 transition-colors hover:text-white" @click="close">
              <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ formError }}</p>

          <form class="space-y-4" @submit.prevent="submitVehicle">
            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                >Vehicle Name *</label
              >
              <input
                v-model="form.name"
                type="text"
                placeholder="Toyota Prado TZG"
                required
                class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
              />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Category</label>
                <select
                  v-model="form.category"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                >
                  <option v-for="cat in catalog.categories" :key="cat.slug" :value="cat.slug">{{ cat.name }}</option>
                </select>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                  >Capacity (pax)</label
                >
                <input
                  v-model="form.passenger_capacity"
                  type="number"
                  min="1"
                  max="50"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                >Price / Day (KES) *</label
              >
              <input
                v-model="form.price_per_day"
                type="number"
                min="0"
                step="0.01"
                placeholder="15000"
                required
                class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Description</label>
              <textarea
                v-model="form.description"
                rows="2"
                class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
              ></textarea>
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">
                Vehicle Photos * <span class="normal-case text-slate-500">(at least 2)</span>
              </label>
              <input
                type="file"
                accept="image/*"
                multiple
                required
                class="w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
                @change="onPhotosSelected"
              />
              <div v-if="photoPreviewUrls.length" class="mt-2 flex flex-wrap gap-2">
                <div v-for="(url, i) in photoPreviewUrls" :key="i" class="group relative h-16 w-24 shrink-0">
                  <img :src="url" alt="Preview" class="h-full w-full rounded-lg border border-navy-700 object-cover" />
                  <button
                    type="button"
                    title="Remove this photo"
                    class="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white opacity-0 transition-opacity group-hover:opacity-100"
                    @click="removePhoto(i)"
                  >
                    &times;
                  </button>
                </div>
              </div>
              <p v-if="photoFiles.length && photoFiles.length < 2" class="mt-1 text-xs text-red-400">
                Add at least one more photo.
              </p>
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                >Logbook / Ownership Document *</label
              >
              <input
                type="file"
                accept="image/*,.pdf"
                required
                class="w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
                @change="logbookFile = $event.target.files[0]"
              />
            </div>

            <div class="flex gap-3 pt-2">
              <button
                type="button"
                class="flex-1 rounded-lg border border-navy-700 py-2.5 text-sm font-semibold text-slate-300 hover:border-slate-500 hover:text-white"
                @click="close"
              >
                Cancel
              </button>
              <button
                type="submit"
                :disabled="saving"
                class="flex-1 rounded-lg bg-gold-500 py-2.5 text-sm font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
              >
                {{ saving ? 'Submitting…' : 'Submit for Review' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
