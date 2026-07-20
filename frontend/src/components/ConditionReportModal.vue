<script setup>
import { computed, reactive, ref } from 'vue'

import apiClient from '../api/client'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  endpoint: { type: String, required: true }, // e.g. /driver/bookings/12/condition-reports/
  reportType: { type: String, required: true }, // 'pickup' | 'return'
})
const emit = defineEmits(['update:modelValue', 'created'])

const title = computed(() => (props.reportType === 'pickup' ? 'Log Pickup Condition' : 'Log Return Condition'))

const saving = ref(false)
const formError = ref('')
const form = reactive({ mileage: '', fuel_level: '', notes: '' })
const photoFiles = ref([])
const photoPreviewUrls = ref([])

function close() {
  emit('update:modelValue', false)
}

function open() {
  Object.assign(form, { mileage: '', fuel_level: '', notes: '' })
  photoFiles.value = []
  photoPreviewUrls.value = []
  formError.value = ''
}

defineExpose({ open })

function onPhotosSelected(event) {
  // Adds to whatever's already picked, rather than replacing it - a file input's own .files
  // list is wiped clean on every selection (see AddVehicleModal.vue's same handling).
  photoFiles.value = [...photoFiles.value, ...Array.from(event.target.files)]
  photoPreviewUrls.value = photoFiles.value.map((file) => URL.createObjectURL(file))
  event.target.value = ''
}

function removePhoto(index) {
  photoFiles.value = photoFiles.value.filter((_, i) => i !== index)
  photoPreviewUrls.value = photoPreviewUrls.value.filter((_, i) => i !== index)
}

async function submit() {
  formError.value = ''
  saving.value = true
  try {
    const payload = new FormData()
    payload.append('report_type', props.reportType)
    if (form.mileage) payload.append('mileage', form.mileage)
    if (form.fuel_level) payload.append('fuel_level', form.fuel_level)
    if (form.notes) payload.append('notes', form.notes)
    photoFiles.value.forEach((file) => payload.append('photos', file))

    const { data } = await apiClient.post(props.endpoint, payload)
    emit('created', data)
    close()
  } catch (err) {
    formError.value = err?.response?.data?.detail || 'Could not save this condition report.'
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
            <h2 class="font-[Georgia] text-xl font-bold text-white">{{ title }}</h2>
            <button class="text-slate-400 transition-colors hover:text-white" @click="close">
              <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ formError }}</p>

          <form class="space-y-4" @submit.prevent="submit">
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Odometer (km)</label>
                <input
                  v-model="form.mileage" type="number" min="0" placeholder="e.g. 45200"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Fuel Level</label>
                <select v-model="form.fuel_level"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none">
                  <option value="">Not noted</option>
                  <option value="empty">Empty</option>
                  <option value="quarter">1/4</option>
                  <option value="half">1/2</option>
                  <option value="three_quarters">3/4</option>
                  <option value="full">Full</option>
                </select>
              </div>
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Notes</label>
              <textarea
                v-model="form.notes" rows="3" placeholder="Existing damage, scratches, anything worth noting"
                class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
              ></textarea>
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Photos</label>
              <input
                type="file" accept="image/*" multiple
                class="w-full text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
                @change="onPhotosSelected"
              />
              <div v-if="photoPreviewUrls.length" class="mt-2 flex flex-wrap gap-2">
                <div v-for="(url, i) in photoPreviewUrls" :key="i" class="group relative h-16 w-24 shrink-0">
                  <img :src="url" alt="Preview" class="h-full w-full rounded-lg border border-navy-700 object-cover" />
                  <button
                    type="button" title="Remove this photo"
                    class="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white opacity-0 transition-opacity group-hover:opacity-100"
                    @click="removePhoto(i)"
                  >
                    &times;
                  </button>
                </div>
              </div>
            </div>

            <div class="flex gap-3 pt-2">
              <button type="button"
                class="flex-1 rounded-lg border border-navy-700 py-2.5 text-sm font-semibold text-slate-300 hover:border-slate-500 hover:text-white"
                @click="close">
                Cancel
              </button>
              <button type="submit" :disabled="saving"
                class="flex-1 rounded-lg bg-gold-500 py-2.5 text-sm font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50">
                {{ saving ? 'Saving…' : 'Save Report' }}
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
.modal-fade-leave-active { transition: opacity 0.2s ease; }
.modal-fade-enter-from,
.modal-fade-leave-to { opacity: 0; }
</style>
