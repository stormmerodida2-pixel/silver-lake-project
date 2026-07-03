<script setup>
import { ref } from 'vue'

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
  } catch (err) {
    error.value = 'Something went wrong. Please try again.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-md px-4 py-16 sm:px-6">
    <h1 class="text-center font-[Georgia] text-3xl font-bold text-white">Forgot Password</h1>

    <div v-if="submitted" class="mt-8 rounded-xl border border-navy-800 bg-navy-900 p-6 text-center">
      <p class="text-sm text-slate-300">
        If {{ email }} is registered, we've sent a link to reset your password. Check your inbox.
      </p>
      <RouterLink to="/login" class="mt-4 inline-block font-semibold text-gold-400 hover:text-gold-300">
        Back to Log In
      </RouterLink>
    </div>

    <form v-else class="mt-8 space-y-4 rounded-xl border border-navy-800 bg-navy-900 p-6" @submit.prevent="submit">
      <p class="text-sm text-slate-400">
        Enter the email you used to sign up and we'll send you a link to reset your password.
      </p>
      <div>
        <label class="mb-1 block text-sm text-slate-300">Email</label>
        <input
          v-model="email"
          type="email"
          required
          class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
        />
      </div>
      <p v-if="error" class="text-sm text-red-400">{{ error }}</p>
      <button
        type="submit"
        :disabled="submitting"
        class="w-full rounded-md bg-gold-500 px-4 py-2 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
      >
        {{ submitting ? 'Sending...' : 'Send Reset Link' }}
      </button>
    </form>
  </div>
</template>
