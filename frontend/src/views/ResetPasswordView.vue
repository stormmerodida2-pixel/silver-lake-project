<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const form = reactive({ newPassword: '', confirmPassword: '' })
const submitting = ref(false)
const error = ref('')
const submitted = ref(false)

async function submit() {
  error.value = ''
  if (form.newPassword !== form.confirmPassword) {
    error.value = 'Passwords do not match.'
    return
  }
  submitting.value = true
  try {
    await auth.confirmPasswordReset(route.params.uid, route.params.token, form.newPassword)
    submitted.value = true
    setTimeout(() => router.push('/login'), 2000)
  } catch (err) {
    const data = err.response?.data
    error.value = data ? Object.values(data).flat().join(' ') : 'This reset link is invalid or has expired.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-md px-4 py-16 sm:px-6">
    <h1 class="text-center font-[Georgia] text-3xl font-bold text-white">Reset Password</h1>

    <div v-if="submitted" class="mt-8 rounded-xl border border-navy-800 bg-navy-900 p-6 text-center">
      <p class="text-sm text-gold-400">Password reset! Redirecting you to log in...</p>
    </div>

    <form v-else class="mt-8 space-y-4 rounded-xl border border-navy-800 bg-navy-900 p-6" @submit.prevent="submit">
      <div>
        <label class="mb-1 block text-sm text-slate-300">New password</label>
        <input
          v-model="form.newPassword"
          type="password"
          required
          class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm text-slate-300">Confirm new password</label>
        <input
          v-model="form.confirmPassword"
          type="password"
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
        {{ submitting ? 'Resetting...' : 'Reset Password' }}
      </button>
    </form>
  </div>
</template>
