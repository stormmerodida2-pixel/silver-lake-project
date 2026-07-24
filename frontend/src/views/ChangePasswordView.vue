<script setup>
import { reactive, ref } from 'vue'

import PasswordInput from '../components/PasswordInput.vue'
import SilverLakeLogo from '../components/SilverLakeLogo.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const form = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
const submitting = ref(false)
const error = ref('')
const success = ref(false)

async function submit() {
  error.value = ''
  success.value = false
  if (form.newPassword !== form.confirmPassword) {
    error.value = 'New passwords do not match.'
    return
  }
  submitting.value = true
  try {
    await auth.changePassword(form.oldPassword, form.newPassword)
    success.value = true
    form.oldPassword = ''
    form.newPassword = ''
    form.confirmPassword = ''
  } catch (err) {
    const data = err.response?.data
    error.value = data ? Object.values(data).flat().join(' ') : 'Could not change your password.'
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
      <h1 class="mt-4 text-center font-[Georgia] text-3xl font-bold text-navy-900">Change Password</h1>

      <form class="mt-8 space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-6" @submit.prevent="submit">
        <div>
          <label class="mb-1 block text-sm text-slate-600">Current password</label>
          <PasswordInput
            v-model="form.oldPassword"
            required
            input-class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
          />
        </div>
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
        <p v-if="success" class="text-sm text-brand-blue-600">Password changed successfully.</p>
        <button
          type="submit"
          :disabled="submitting"
          class="w-full rounded-md bg-gold-500 px-4 py-2 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
        >
          {{ submitting ? 'Saving...' : 'Change Password' }}
        </button>
      </form>
    </div>
  </div>
</template>
