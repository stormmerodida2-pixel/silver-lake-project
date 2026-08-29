<script setup>
import { reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import PhoneInput from '../PhoneInput.vue'

defineProps({
  modelValue: { type: Boolean, required: true },
  driverOptions: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'created'])

// The parent view doesn't already load the full fleet (only its own driver list) - staff need
// to be able to book any vehicle here, not just ones with a driver already attached.
const { items: vehicleOptions, load: loadVehicleOptions } = useAdminList('/admin/fleet/')

const saving = ref(false)
const error = ref('')
const today = new Date().toISOString().split('T')[0]
const form = reactive({
  vehicle: '',
  driver: '',
  service_type: 'with_driver',
  customer_name: '',
  customer_phone: '',
  customer_email: '',
  pickup_location: '',
  dropoff_location: '',
  start_date: '',
  end_date: '',
  notes: '',
})
const result = ref(null) // { booking, payment_url } after creation

function close() {
  emit('update:modelValue', false)
}

function open() {
  Object.assign(form, {
    vehicle: '',
    driver: '',
    service_type: 'with_driver',
    customer_name: '',
    customer_phone: '',
    customer_email: '',
    pickup_location: '',
    dropoff_location: '',
    start_date: '',
    end_date: '',
    notes: '',
  })
  error.value = ''
  result.value = null
  loadVehicleOptions()
}

defineExpose({ open })

async function submit() {
  error.value = ''
  saving.value = true
  try {
    const { data } = await apiClient.post('/admin/bookings/create-direct/', {
      ...form,
      driver: form.driver || null,
    })
    result.value = data
    emit('created', data.booking)
  } catch (err) {
    const detail = err?.response?.data
    error.value = typeof detail === 'object' ? Object.values(detail).flat().join(' ') : 'Could not create this booking.'
  } finally {
    saving.value = false
  }
}

async function copyPaymentLink() {
  if (!result.value) return
  await navigator.clipboard.writeText(result.value.payment_url)
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
        <div class="w-full max-w-lg rounded-2xl border border-border bg-surface p-8 shadow-2xl">
          <div class="mb-6 flex items-center justify-between">
            <h2 class="font-[Georgia] text-xl font-bold text-foreground">
              {{ result ? 'Booking Created' : 'New Direct Booking' }}
            </h2>
            <button class="text-foreground-muted transition-colors hover:text-foreground" @click="close">
              <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- Result: the whole point of this flow is the shareable payment link, front and
               center - unlike the driver on-site modal, this customer usually isn't standing in
               front of anyone, so there's no in-person payment collection to offer first. -->
          <div v-if="result" class="space-y-4">
            <p class="text-sm text-foreground-secondary">
              Booking created for <strong>{{ result.booking.customer_name }}</strong
              >. Share this link with them to pay - no account needed.
            </p>

            <div class="flex items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 py-2">
              <span class="flex-1 truncate text-xs text-foreground-secondary">{{ result.payment_url }}</span>
              <button
                class="shrink-0 rounded-md bg-accent-bg px-3 py-1 text-xs font-semibold text-on-accent hover:bg-accent-bg-hover"
                @click="copyPaymentLink"
              >
                Copy
              </button>
            </div>
            <a
              :href="`https://wa.me/?text=${encodeURIComponent('Here is your SilverLake payment link: ' + result.payment_url)}`"
              target="_blank"
              rel="noopener noreferrer"
              class="flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-500 py-2.5 text-sm font-semibold text-success hover:bg-emerald-500 hover:text-on-accent"
            >
              Share via WhatsApp
            </a>

            <button
              class="w-full rounded-lg border border-border py-2.5 text-sm font-semibold text-foreground-secondary hover:border-slate-500 hover:text-foreground"
              @click="close"
            >
              Done
            </button>
          </div>

          <!-- Form -->
          <form v-else class="space-y-4" @submit.prevent="submit">
            <p v-if="error" class="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-danger">{{ error }}</p>
            <p class="rounded-lg bg-accent-bg/10 px-4 py-3 text-xs text-accent-strong">
              For a phone/WhatsApp lead not yet tied to a specific driver or a registered company. Confirms
              immediately with no deposit required - you're vouching for this booking in a real conversation.
            </p>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                  >Service Type</label
                >
                <select
                  v-model="form.service_type"
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
                >
                  <option value="with_driver">With Driver</option>
                  <option value="self_drive">Self Drive</option>
                </select>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted">Vehicle *</label>
                <select
                  v-model.number="form.vehicle"
                  required
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
                >
                  <option value="" disabled>Select a vehicle</option>
                  <option v-for="v in vehicleOptions" :key="v.id" :value="v.id">{{ v.name }}</option>
                </select>
              </div>
            </div>

            <div v-if="form.service_type === 'with_driver'">
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                >Driver (optional)</label
              >
              <select
                v-model.number="form.driver"
                class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
              >
                <option value="">No driver assigned yet</option>
                <option v-for="d in driverOptions" :key="d.id" :value="d.id">{{ d.full_name }}</option>
              </select>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                  >Client Name *</label
                >
                <input
                  v-model="form.customer_name"
                  type="text"
                  required
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted">Phone *</label>
                <PhoneInput v-model="form.customer_phone" required />
              </div>
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                >Email (optional)</label
              >
              <input
                v-model="form.customer_email"
                type="email"
                class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
              />
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                  >Start Date *</label
                >
                <input
                  v-model="form.start_date"
                  type="date"
                  :min="today"
                  required
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted">End Date *</label>
                <input
                  v-model="form.end_date"
                  type="date"
                  :min="form.start_date || today"
                  required
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                >Pickup Location *</label
              >
              <input
                v-model="form.pickup_location"
                type="text"
                required
                class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                >Drop-off Location (optional)</label
              >
              <input
                v-model="form.dropoff_location"
                type="text"
                class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
              />
            </div>

            <div class="flex gap-3 pt-2">
              <button
                type="button"
                class="flex-1 rounded-lg border border-border py-2.5 text-sm font-semibold text-foreground-secondary hover:border-slate-500 hover:text-foreground"
                @click="close"
              >
                Cancel
              </button>
              <button
                type="submit"
                :disabled="saving"
                class="flex-1 rounded-lg bg-accent-bg py-2.5 text-sm font-semibold text-on-accent hover:bg-accent-bg-hover disabled:opacity-50"
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
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
