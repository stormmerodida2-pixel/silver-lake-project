<script setup>
import { reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import PhoneInput from '../PhoneInput.vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  driverOptions: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'created'])

// Own vehicle list - the parent view doesn't already load one (only drivers, for the
// existing driver-reassignment dropdown), and this is the only place in the admin dashboard
// that needs it.
const { items: vehicleOptions, load: loadVehicleOptions } = useAdminList('/admin/fleet/')

const saving = ref(false)
const error = ref('')
const today = new Date().toISOString().split('T')[0]
const form = reactive({
  vehicle: '', driver: '', service_type: 'with_driver', customer_name: '', customer_phone: '',
  customer_email: '', pickup_location: '', dropoff_location: '', start_date: '', end_date: '',
  government_contract_reference: '', notes: '',
})

function close() {
  emit('update:modelValue', false)
}

function open() {
  Object.assign(form, {
    vehicle: '', driver: '', service_type: 'with_driver', customer_name: '', customer_phone: '',
    customer_email: '', pickup_location: '', dropoff_location: '', start_date: '', end_date: '',
    government_contract_reference: '', notes: '',
  })
  error.value = ''
  loadVehicleOptions()
}

defineExpose({ open })

async function submit() {
  error.value = ''
  saving.value = true
  try {
    const { data } = await apiClient.post('/admin/bookings/create-government/', {
      ...form,
      driver: form.driver || null,
    })
    emit('created', data)
    close()
  } catch (err) {
    const detail = err?.response?.data
    error.value = typeof detail === 'object'
      ? Object.values(detail).flat().join(' ')
      : 'Could not create this booking.'
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
            <h2 class="font-[Georgia] text-xl font-bold text-white">New Contract Booking</h2>
            <button class="text-slate-400 transition-colors hover:text-white" @click="close">
              <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <form class="space-y-4" @submit.prevent="submit">
            <p v-if="error" class="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ error }}</p>
            <p class="rounded-lg bg-gold-500/10 px-4 py-3 text-xs text-gold-300">
              Confirms immediately with no deposit required - billed separately per the contract's own terms.
            </p>

            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Contract Reference *</label>
              <input
                v-model="form.government_contract_reference" type="text" required
                placeholder="e.g. Ministry of Health - LPO#4821"
                class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
              />
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Service Type</label>
                <select
                  v-model="form.service_type"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                >
                  <option value="with_driver">With Driver</option>
                  <option value="self_drive">Self Drive</option>
                </select>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Vehicle *</label>
                <select
                  v-model.number="form.vehicle" required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                >
                  <option value="" disabled>Select a vehicle</option>
                  <option v-for="v in vehicleOptions" :key="v.id" :value="v.id">{{ v.name }}</option>
                </select>
              </div>
            </div>

            <div v-if="form.service_type === 'with_driver'">
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Driver (optional)</label>
              <select
                v-model.number="form.driver"
                class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
              >
                <option value="">No driver assigned yet</option>
                <option v-for="d in driverOptions" :key="d.id" :value="d.id">{{ d.full_name }}</option>
              </select>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Department Contact *</label>
                <input
                  v-model="form.customer_name" type="text" required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Phone *</label>
                <PhoneInput v-model="form.customer_phone" required dark />
              </div>
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Email (optional)</label>
              <input
                v-model="form.customer_email" type="email"
                class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
              />
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Start Date *</label>
                <input
                  v-model="form.start_date" type="date" :min="today" required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">End Date *</label>
                <input
                  v-model="form.end_date" type="date" :min="form.start_date || today" required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Pickup Location *</label>
              <input
                v-model="form.pickup_location" type="text" required
                class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Drop-off Location (optional)</label>
              <input
                v-model="form.dropoff_location" type="text"
                class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
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
                type="submit" :disabled="saving"
                class="flex-1 rounded-lg bg-gold-500 py-2.5 text-sm font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
              >
                {{ saving ? 'Creating…' : 'Create Booking' }}
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
