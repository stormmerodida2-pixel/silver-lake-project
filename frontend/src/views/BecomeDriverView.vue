<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../api/client'
import PhoneInput from '../components/PhoneInput.vue'
import { useAuthStore } from '../stores/auth'
import { useCatalogStore } from '../stores/catalog'
import { trackEvent } from '../utils/analytics'

const auth = useAuthStore()
const catalog = useCatalogStore()

onMounted(() => {
  catalog.fetchCategories()
})

const firstName = ref('')
const lastName = ref('')

const form = reactive({
  email: '',
  phone_number: '',
  years_of_experience: '',
  bio: '',
  license_number: '',
  vehicle_name: '',
  vehicle_category: '',
  passenger_capacity: '',
  price_per_day: '',
})

const licenseDocument = ref(null)
const vehiclePhoto = ref(null)
const vehicleLogbookDocument = ref(null)

const submitting = ref(false)
const submitted = ref(false)
const error = ref('')

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    const payload = new FormData()
    // Backend/Driver record still stores one combined full_name field - only the form itself
    // collects first/last separately, for a clearer, less ambiguous "what goes where" than one
    // free-text name field.
    payload.append('full_name', `${firstName.value.trim()} ${lastName.value.trim()}`.trim())
    Object.entries(form).forEach(([key, value]) => payload.append(key, value))
    payload.append('license_document', licenseDocument.value)
    if (vehiclePhoto.value) payload.append('vehicle_photo', vehiclePhoto.value)
    if (vehicleLogbookDocument.value) payload.append('vehicle_logbook_document', vehicleLogbookDocument.value)

    await apiClient.post('/drivers/apply/', payload)
    submitted.value = true
    trackEvent('generate_lead', { lead_type: 'driver_application' })
  } catch (err) {
    const data = err.response?.data
    error.value = data ? Object.values(data).flat().join(' ') : 'Could not submit your application.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="bg-page">
    <div class="mx-auto max-w-2xl px-4 py-16 sm:px-6">
      <h1 class="text-center font-[Georgia] text-3xl font-bold text-foreground">Become a Driver</h1>
      <p class="mt-2 text-center text-foreground-muted">
        Drive for SilverLake with your own vehicle. Submit your details below - our team reviews every application
        before you and your car go live on the platform.
      </p>

      <div
        v-if="auth.user?.driver_status === 'active'"
        class="mt-10 rounded-xl border border-border-subtle bg-surface p-6 text-center"
      >
        <h2 class="font-[Georgia] text-xl font-bold text-accent">You're already a driver-partner!</h2>
        <p class="mt-2 text-sm text-foreground-muted">
          Head to your
          <RouterLink to="/driver" class="font-semibold text-accent hover:underline"
            >Driver Dashboard</RouterLink
          >
          to manage your vehicles and availability.
        </p>
      </div>

      <div
        v-else-if="auth.user?.driver_status === 'suspended'"
        class="mt-10 rounded-xl border border-red-500/30 bg-red-500/10 p-6 text-center"
      >
        <h2 class="font-[Georgia] text-xl font-bold text-danger">Currently Suspended</h2>
        <p class="mt-2 text-sm text-danger">
          Your driver-partner account is currently suspended. Contact us if you believe this was a mistake.
        </p>
      </div>

      <div v-else-if="submitted" class="mt-10 rounded-xl border border-border-subtle bg-surface p-6 text-center">
        <h2 class="font-[Georgia] text-xl font-bold text-accent">Application received!</h2>
        <p class="mt-2 text-sm text-foreground-muted">
          We'll review your documents and vehicle details, then contact you at {{ form.email }} or
          {{ form.phone_number }}.
        </p>
        <RouterLink
          to="/"
          class="mt-4 inline-block rounded-md bg-accent-bg px-5 py-2.5 font-semibold text-on-accent transition hover:bg-accent-bg-hover"
        >
          Back to Home
        </RouterLink>
      </div>

      <form v-else class="mt-10 space-y-6 rounded-xl border border-border-subtle bg-surface p-6" @submit.prevent="submit">
        <div>
          <h3 class="text-sm font-semibold uppercase tracking-wide text-accent">About You</h3>
          <div class="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">First name</label>
              <input
                v-model="firstName"
                type="text"
                required
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Last name</label>
              <input
                v-model="lastName"
                type="text"
                required
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Phone number</label>
              <PhoneInput v-model="form.phone_number" required dark />
            </div>
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Email</label>
              <input
                v-model="form.email"
                type="email"
                required
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Years of driving experience</label>
              <input
                v-model="form.years_of_experience"
                type="number"
                min="0"
                required
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              />
            </div>
          </div>
          <div class="mt-4">
            <label class="mb-1 block text-sm text-foreground-muted">Short bio</label>
            <textarea
              v-model="form.bio"
              rows="3"
              class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
            ></textarea>
          </div>
        </div>

        <div>
          <h3 class="text-sm font-semibold uppercase tracking-wide text-accent">License</h3>
          <div class="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">License number</label>
              <input
                v-model="form.license_number"
                type="text"
                required
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">License document (photo or PDF)</label>
              <input
                type="file"
                required
                accept="image/*,.pdf"
                class="w-full text-sm text-foreground-muted file:mr-3 file:rounded-md file:border-0 file:bg-accent-bg file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-on-accent"
                @change="licenseDocument = $event.target.files[0]"
              />
            </div>
          </div>
        </div>

        <div>
          <h3 class="text-sm font-semibold uppercase tracking-wide text-accent">Your Vehicle</h3>
          <div class="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Vehicle name</label>
              <input
                v-model="form.vehicle_name"
                type="text"
                placeholder="e.g. Toyota Noah"
                required
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Category</label>
              <select
                v-model="form.vehicle_category"
                required
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              >
                <option value="" disabled>Select a category</option>
                <option v-for="cat in catalog.categories" :key="cat.slug" :value="cat.slug">{{ cat.name }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Passenger capacity</label>
              <input
                v-model="form.passenger_capacity"
                type="number"
                min="1"
                required
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Proposed price per day (KES)</label>
              <input
                v-model="form.price_per_day"
                type="number"
                min="0"
                required
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Vehicle photo (optional)</label>
              <input
                type="file"
                accept="image/*"
                class="w-full text-sm text-foreground-muted file:mr-3 file:rounded-md file:border-0 file:bg-accent-bg file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-on-accent"
                @change="vehiclePhoto = $event.target.files[0]"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Logbook / proof of ownership (optional)</label>
              <input
                type="file"
                accept="image/*,.pdf"
                class="w-full text-sm text-foreground-muted file:mr-3 file:rounded-md file:border-0 file:bg-accent-bg file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-on-accent"
                @change="vehicleLogbookDocument = $event.target.files[0]"
              />
            </div>
          </div>
        </div>

        <p v-if="error" class="text-sm text-danger">{{ error }}</p>

        <button
          type="submit"
          :disabled="submitting"
          class="w-full rounded-md bg-accent-bg px-4 py-2 font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
        >
          {{ submitting ? 'Submitting...' : 'Submit Application' }}
        </button>
      </form>
    </div>
  </div>
</template>
