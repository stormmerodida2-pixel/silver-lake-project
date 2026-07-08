<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const form = reactive({ first_name: '', last_name: '', phone_number: '' })
const email = ref('')
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const success = ref(false)

async function loadProfile() {
  loading.value = true
  try {
    const { data } = await apiClient.get('/auth/me/')
    form.first_name = data.first_name
    form.last_name = data.last_name
    form.phone_number = data.phone_number
    email.value = data.email
  } catch (err) {
    error.value = 'Could not load your profile.'
  } finally {
    loading.value = false
  }
}

async function submit() {
  error.value = ''
  success.value = false
  submitting.value = true
  try {
    const { data } = await apiClient.patch('/auth/me/', form)
    form.first_name = data.first_name
    form.last_name = data.last_name
    form.phone_number = data.phone_number
    success.value = true
  } catch (err) {
    const data = err.response?.data
    error.value = data ? Object.values(data).flat().join(' ') : 'Could not update your profile.'
  } finally {
    submitting.value = false
  }
}

onMounted(loadProfile)
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-2xl px-4 py-16 sm:px-6 lg:py-20">
      <h1 class="text-center font-[Georgia] text-4xl font-bold text-navy-900">My Profile</h1>
      <p class="mt-3 text-center text-base text-slate-500">Update your name and contact details.</p>

      <p v-if="loading" class="mt-10 text-center text-slate-500">Loading...</p>

      <form v-else class="mt-10 space-y-6 rounded-2xl border border-slate-200 bg-slate-50 p-8 sm:p-10" @submit.prevent="submit">
        <div class="grid gap-5 sm:grid-cols-2">
          <div>
            <label class="mb-1.5 block text-sm font-medium text-slate-600">First name</label>
            <input
              v-model="form.first_name"
              type="text"
              required
              class="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-base text-navy-900 focus:border-brand-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-sm font-medium text-slate-600">Last name</label>
            <input
              v-model="form.last_name"
              type="text"
              class="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-base text-navy-900 focus:border-brand-blue-500 focus:outline-none"
            />
          </div>
        </div>

        <div>
          <label class="mb-1.5 block text-sm font-medium text-slate-600">Phone number</label>
          <input
            v-model="form.phone_number"
            type="tel"
            placeholder="2547XXXXXXXX"
            class="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-base text-navy-900 focus:border-brand-blue-500 focus:outline-none"
          />
        </div>

        <div>
          <label class="mb-1.5 block text-sm font-medium text-slate-600">Email</label>
          <input
            :value="email"
            type="email"
            disabled
            class="w-full cursor-not-allowed rounded-lg border border-slate-200 bg-slate-100 px-4 py-3 text-base text-slate-500"
          />
          <p class="mt-1.5 text-xs text-slate-400">Your email is also your login - contact us if you need it changed.</p>
        </div>

        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
        <p v-if="success" class="text-sm text-brand-blue-600">Profile updated.</p>

        <button
          type="submit"
          :disabled="submitting"
          class="w-full rounded-lg bg-gold-500 px-4 py-3 text-base font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
        >
          {{ submitting ? 'Saving...' : 'Save Changes' }}
        </button>
      </form>

      <p class="mt-6 text-center text-sm text-slate-500">
        Want to change your password instead?
        <RouterLink to="/account/change-password" class="font-semibold text-brand-blue-600 hover:underline">
          Change Password
        </RouterLink>
      </p>
    </div>
  </div>
</template>
