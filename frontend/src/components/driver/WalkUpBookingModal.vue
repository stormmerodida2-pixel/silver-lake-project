<script setup>
import { reactive, ref } from 'vue'

import apiClient from '../../api/client'
import PhoneInput from '../PhoneInput.vue'
import { useDriverPortalStore } from '../../stores/driverPortal'
import BookingPaymentCollector from './BookingPaymentCollector.vue'

defineProps({
  modelValue: { type: Boolean, required: true },
})
const emit = defineEmits(['update:modelValue'])

const driverPortal = useDriverPortalStore()

const onsiteSaving = ref(false)
const onsiteError = ref('')
const onsiteForm = reactive({
  vehicle: '',
  customer_name: '',
  customer_phone: '',
  customer_email: '',
  pickup_location: '',
  dropoff_location: '',
  start_date: '',
  end_date: '',
  notes: '',
})
const onsiteResult = ref(null) // { booking, payment_url } after creation
const today = new Date().toISOString().split('T')[0]

function close() {
  emit('update:modelValue', false)
}

function open() {
  Object.assign(onsiteForm, {
    vehicle: '',
    customer_name: '',
    customer_phone: '',
    customer_email: '',
    pickup_location: '',
    dropoff_location: '',
    start_date: '',
    end_date: '',
    notes: '',
  })
  onsiteError.value = ''
  onsiteResult.value = null
}

defineExpose({ open })

async function submitOnsiteBooking() {
  onsiteError.value = ''
  onsiteSaving.value = true
  try {
    const { data } = await apiClient.post('/driver/bookings/create/', onsiteForm)
    onsiteResult.value = data
    driverPortal.addBooking(data.booking)
  } catch (err) {
    const detail = err?.response?.data
    onsiteError.value =
      typeof detail === 'object' ? Object.values(detail).flat().join(' ') : 'Could not create this booking.'
  } finally {
    onsiteSaving.value = false
  }
}

async function copyPaymentLink() {
  if (!onsiteResult.value) return
  await navigator.clipboard.writeText(onsiteResult.value.payment_url)
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
              {{ onsiteResult ? 'Booking Created' : 'Book For a Client On-Site' }}
            </h2>
            <button class="text-foreground-muted transition-colors hover:text-foreground" @click="close">
              <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- Result: collect payment (method + exact amount), fall back to sharing the link -->
          <div v-if="onsiteResult" class="space-y-4">
            <p class="text-sm text-foreground-secondary">
              Booking created for <strong>{{ onsiteResult.booking.customer_name }}</strong
              >. Ask how they're paying and the exact amount.
            </p>

            <div class="rounded-lg border border-border bg-surface-2/50 p-4">
              <BookingPaymentCollector :booking="onsiteResult.booking" />
            </div>

            <details class="text-sm text-foreground-muted">
              <summary class="cursor-pointer select-none font-semibold text-foreground-secondary">
                Or share a payment link instead
              </summary>
              <div class="mt-2 flex items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 py-2">
                <span class="flex-1 truncate text-xs text-foreground-secondary">{{ onsiteResult.payment_url }}</span>
                <button
                  class="shrink-0 rounded-md bg-accent-bg px-3 py-1 text-xs font-semibold text-on-accent hover:bg-accent-bg-hover"
                  @click="copyPaymentLink"
                >
                  Copy
                </button>
              </div>
              <a
                :href="`https://wa.me/?text=${encodeURIComponent('Here is your SilverLake payment link: ' + onsiteResult.payment_url)}`"
                target="_blank"
                rel="noopener noreferrer"
                class="mt-2 flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-500 py-2.5 text-sm font-semibold text-success hover:bg-emerald-500 hover:text-on-accent"
              >
                Share via WhatsApp
              </a>
            </details>

            <button
              class="w-full rounded-lg border border-border py-2.5 text-sm font-semibold text-foreground-secondary hover:border-slate-500 hover:text-foreground"
              @click="close"
            >
              Done
            </button>
          </div>

          <!-- Form -->
          <form v-else class="space-y-4" @submit.prevent="submitOnsiteBooking">
            <p v-if="onsiteError" class="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-danger">{{ onsiteError }}</p>

            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted">Vehicle *</label>
              <select
                v-model.number="onsiteForm.vehicle"
                required
                class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
              >
                <option value="" disabled>Select one of your vehicles</option>
                <option v-for="v in driverPortal.profile.vehicles" :key="v.id" :value="v.id">{{ v.name }}</option>
              </select>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                  >Client Name *</label
                >
                <input
                  v-model="onsiteForm.customer_name"
                  type="text"
                  required
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted">Phone *</label>
                <PhoneInput v-model="onsiteForm.customer_phone" required />
              </div>
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                >Email (optional)</label
              >
              <input
                v-model="onsiteForm.customer_email"
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
                  v-model="onsiteForm.start_date"
                  type="date"
                  :min="today"
                  required
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground focus:border-accent-border-strong focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted">End Date *</label>
                <input
                  v-model="onsiteForm.end_date"
                  type="date"
                  :min="onsiteForm.start_date || today"
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
                v-model="onsiteForm.pickup_location"
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
                v-model="onsiteForm.dropoff_location"
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
                :disabled="onsiteSaving"
                class="flex-1 rounded-lg bg-accent-bg py-2.5 text-sm font-semibold text-on-accent hover:bg-accent-bg-hover disabled:opacity-50"
              >
                {{ onsiteSaving ? 'Creating…' : 'Create Booking' }}
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
