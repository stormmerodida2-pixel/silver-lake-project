<script setup>
import { ref } from 'vue'

import SilverLakeLogo from '../components/SilverLakeLogo.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const email = ref('')
const submitting = ref(false)
const submitted = ref(false)
const error = ref('')

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await auth.requestPasswordReset(email.value)
    submitted.value = true
  } catch {
    error.value = 'Something went wrong. Please try again.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-md px-4 py-16 sm:px-6">
      <RouterLink to="/" class="flex items-center justify-center gap-2">
        <SilverLakeLogo :size="48" />
        <span class="flex flex-col items-start leading-none">
          <span class="font-[Georgia] text-xl font-bold uppercase tracking-wide text-navy-900">SilverLake</span>
          <span
            class="mt-1 border-b-2 border-gold-500 pb-0.5 text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500"
          >
            Car Rentals
          </span>
        </span>
      </RouterLink>
      <h1 class="mt-4 text-center font-[Georgia] text-3xl font-bold text-navy-900">Forgot Password</h1>

      <div v-if="submitted" class="mt-8 rounded-xl border border-slate-200 bg-slate-50 p-6 text-center">
        <p class="text-sm text-slate-600">
          If {{ email }} is registered, we've sent a link to reset your password. Check your inbox.
        </p>
        <RouterLink to="/login" class="mt-4 inline-block font-semibold text-brand-blue-600 hover:text-brand-blue-500">
          Back to Log In
        </RouterLink>
      </div>

      <form v-else class="mt-8 space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-6" @submit.prevent="submit">
        <p class="text-sm text-slate-500">
          Enter the email you used to sign up and we'll send you a link to reset your password.
        </p>
        <div>
          <label class="mb-1 block text-sm text-slate-600">Email</label>
          <input
            v-model="email"
            type="email"
            required
            class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
          />
        </div>
        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
        <button
          type="submit"
          :disabled="submitting"
          class="w-full rounded-md bg-gold-500 px-4 py-2 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
        >
          {{ submitting ? 'Sending...' : 'Send Reset Link' }}
        </button>
      </form>
    </div>
  </div>
</template>
