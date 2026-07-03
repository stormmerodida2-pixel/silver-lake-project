<script setup>
import { reactive, ref } from 'vue'

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
  <div class="mx-auto max-w-md px-4 py-16 sm:px-6">
    <h1 class="text-center font-[Georgia] text-3xl font-bold text-white">Change Password</h1>

    <form class="mt-8 space-y-4 rounded-xl border border-navy-800 bg-navy-900 p-6" @submit.prevent="submit">
      <div>
        <label class="mb-1 block text-sm text-slate-300">Current password</label>
        <input
          v-model="form.oldPassword"
          type="password"
          required
          class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
        />
      </div>
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
      <p v-if="success" class="text-sm text-gold-400">Password changed successfully.</p>
      <button
        type="submit"
        :disabled="submitting"
        class="w-full rounded-md bg-gold-500 px-4 py-2 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
      >
        {{ submitting ? 'Saving...' : 'Change Password' }}
      </button>
    </form>
  </div>
</template>
