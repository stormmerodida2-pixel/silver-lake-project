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
  <div class="bg-page">
    <div class="mx-auto max-w-md px-4 py-16 sm:px-6">
      <RouterLink to="/" class="flex items-center justify-center gap-2">
        <SilverLakeLogo :size="48" />
        <span class="flex flex-col items-start leading-none">
          <span class="font-[Georgia] text-xl font-bold uppercase tracking-wide text-foreground">SilverLake</span>
          <span
            class="mt-1 border-b-2 border-accent-border-strong pb-0.5 text-[11px] font-bold uppercase tracking-[0.2em] text-foreground-muted"
          >
            Car Rentals
          </span>
        </span>
      </RouterLink>
      <h1 class="mt-4 text-center font-[Georgia] text-3xl font-bold text-foreground">Reset Password</h1>

      <div v-if="submitted" class="mt-8 rounded-xl border border-border-subtle bg-surface p-6 text-center">
        <p class="text-sm text-success">Password reset! Redirecting you to log in...</p>
      </div>

      <form v-else class="mt-8 space-y-4 rounded-xl border border-border-subtle bg-surface p-6" @submit.prevent="submit">
        <div>
          <label class="mb-1 block text-sm text-foreground-muted">New password</label>
          <PasswordInput
            v-model="form.newPassword"
            required
            input-class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm text-foreground-muted">Confirm new password</label>
          <PasswordInput
            v-model="form.confirmPassword"
            required
            input-class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
          />
        </div>
        <p v-if="error" class="text-sm text-danger">{{ error }}</p>
        <button
          type="submit"
          :disabled="submitting"
          class="w-full rounded-md bg-accent-bg px-4 py-2 font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
        >
          {{ submitting ? 'Resetting...' : 'Reset Password' }}
        </button>
      </form>
    </div>
  </div>
</template>
