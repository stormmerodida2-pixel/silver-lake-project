<script setup>
import { reactive, ref } from 'vue'

import apiClient from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const categories = [
  { value: 'executive_suv', label: 'Executive SUV' },
  { value: 'premium_mpv', label: 'Premium MPV' },
  { value: 'compact_sedan', label: 'Compact Sedan' },
  { value: 'passenger_van', label: 'Passenger Van' },
]

const form = reactive({
  full_name: '',
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
    Object.entries(form).forEach(([key, value]) => payload.append(key, value))
    payload.append('license_document', licenseDocument.value)
    if (vehiclePhoto.value) payload.append('vehicle_photo', vehiclePhoto.value)
    if (vehicleLogbookDocument.value) payload.append('vehicle_logbook_document', vehicleLogbookDocument.value)

    await apiClient.post('/drivers/apply/', payload)
    submitted.value = true
  } catch (err) {
    const data = err.response?.data
    error.value = data ? Object.values(data).flat().join(' ') : 'Could not submit your application.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-2xl px-4 py-16 sm:px-6">
      <h1 class="text-center font-[Georgia] text-3xl font-bold text-navy-900">Become a Driver</h1>
      <p class="mt-2 text-center text-slate-600">
        Drive for SilverLake with your own vehicle. Submit your details below - our team reviews every
        application before you and your car go live on the platform.
      </p>

      <div v-if="auth.user?.driver_status === 'active'" class="mt-10 rounded-xl border border-slate-200 bg-slate-50 p-6 text-center">
        <h2 class="font-[Georgia] text-xl font-bold text-brand-blue-600">You're already a driver-partner!</h2>
        <p class="mt-2 text-sm text-slate-600">
          Head to your <RouterLink to="/driver" class="font-semibold text-brand-blue-600 hover:underline">Driver Dashboard</RouterLink>
          to manage your vehicles and availability.
        </p>
      </div>

      <div v-else-if="auth.user?.driver_status === 'suspended'" class="mt-10 rounded-xl border border-red-200 bg-red-50 p-6 text-center">
        <h2 class="font-[Georgia] text-xl font-bold text-red-700">Currently Suspended</h2>
        <p class="mt-2 text-sm text-red-700">
          Your driver-partner account is currently suspended. Contact us if you believe this was a mistake.
        </p>
      </div>

      <div v-else-if="submitted" class="mt-10 rounded-xl border border-slate-200 bg-slate-50 p-6 text-center">
        <h2 class="font-[Georgia] text-xl font-bold text-brand-blue-600">Application received!</h2>
        <p class="mt-2 text-sm text-slate-600">
          We'll review your documents and vehicle details, then contact you at {{ form.email }} or
          {{ form.phone_number }}.
        </p>
        <RouterLink
          to="/"
          class="mt-4 inline-block rounded-md bg-gold-500 px-5 py-2.5 font-semibold text-navy-950 transition hover:bg-gold-400"
        >
          Back to Home
        </RouterLink>
      </div>

      <form v-else class="mt-10 space-y-6 rounded-xl border border-slate-200 bg-slate-50 p-6" @submit.prevent="submit">
        <div>
          <h3 class="text-sm font-semibold uppercase tracking-wide text-brand-blue-600">About You</h3>
          <div class="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <label class="mb-1 block text-sm text-slate-600">Full name</label>
              <input
                v-model="form.full_name"
                type="text"
                required
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-slate-600">Phone number</label>
              <input
                v-model="form.phone_number"
                type="tel"
                placeholder="2547XXXXXXXX"
                required
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-slate-600">Email</label>
              <input
                v-model="form.email"
                type="email"
                required
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-slate-600">Years of driving experience</label>
              <input
                v-model="form.years_of_experience"
                type="number"
                min="0"
                required
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              />
            </div>
          </div>
          <div class="mt-4">
            <label class="mb-1 block text-sm text-slate-600">Short bio</label>
            <textarea
              v-model="form.bio"
              rows="3"
              class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
            ></textarea>
          </div>
        </div>

        <div>
          <h3 class="text-sm font-semibold uppercase tracking-wide text-brand-blue-600">License</h3>
          <div class="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <label class="mb-1 block text-sm text-slate-600">License number</label>
              <input
                v-model="form.license_number"
                type="text"
                required
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-slate-600">License document (photo or PDF)</label>
              <input
                type="file"
                required
                accept="image/*,.pdf"
                class="w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
                @change="licenseDocument = $event.target.files[0]"
              />
            </div>
          </div>
        </div>

        <div>
          <h3 class="text-sm font-semibold uppercase tracking-wide text-brand-blue-600">Your Vehicle</h3>
          <div class="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <label class="mb-1 block text-sm text-slate-600">Vehicle name</label>
              <input
                v-model="form.vehicle_name"
                type="text"
                placeholder="e.g. Toyota Noah"
                required
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-slate-600">Category</label>
              <select
                v-model="form.vehicle_category"
                required
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              >
                <option value="" disabled>Select a category</option>
                <option v-for="cat in categories" :key="cat.value" :value="cat.value">{{ cat.label }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm text-slate-600">Passenger capacity</label>
              <input
                v-model="form.passenger_capacity"
                type="number"
                min="1"
                required
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-slate-600">Proposed price per day (KES)</label>
              <input
                v-model="form.price_per_day"
                type="number"
                min="0"
                required
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-slate-600">Vehicle photo (optional)</label>
              <input
                type="file"
                accept="image/*"
                class="w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
                @change="vehiclePhoto = $event.target.files[0]"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm text-slate-600">Logbook / proof of ownership (optional)</label>
              <input
                type="file"
                accept="image/*,.pdf"
                class="w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-gold-500 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-navy-950"
                @change="vehicleLogbookDocument = $event.target.files[0]"
              />
            </div>
          </div>
        </div>

        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>

        <button
          type="submit"
          :disabled="submitting"
          class="w-full rounded-md bg-gold-500 px-4 py-2 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
        >
          {{ submitting ? 'Submitting...' : 'Submit Application' }}
        </button>
      </form>
    </div>
  </div>
</template>
