<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PasswordInput from '../components/PasswordInput.vue'
import SilverLakeLogo from '../components/SilverLakeLogo.vue'
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
  <div class="bg-white">
    <div class="mx-auto max-w-md px-4 py-16 sm:px-6">
      <RouterLink to="/" class="flex justify-center">
        <SilverLakeLogo :size="48" />
      </RouterLink>
      <h1 class="mt-4 text-center font-[Georgia] text-3xl font-bold text-navy-900">Reset Password</h1>

      <div v-if="submitted" class="mt-8 rounded-xl border border-slate-200 bg-slate-50 p-6 text-center">
        <p class="text-sm text-brand-blue-600">Password reset! Redirecting you to log in...</p>
      </div>

      <form v-else class="mt-8 space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-6" @submit.prevent="submit">
        <div>
          <label class="mb-1 block text-sm text-slate-600">New password</label>
          <PasswordInput
            v-model="form.newPassword"
            required
            input-class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm text-slate-600">Confirm new password</label>
          <PasswordInput
            v-model="form.confirmPassword"
            required
            input-class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
          />
        </div>
        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
        <button
          type="submit"
          :disabled="submitting"
          class="w-full rounded-md bg-gold-500 px-4 py-2 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
        >
          {{ submitting ? 'Resetting...' : 'Reset Password' }}
        </button>
      </form>
    </div>
  </div>
</template>
