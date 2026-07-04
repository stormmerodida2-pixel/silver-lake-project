<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const form = reactive({ email: '', password: '' })
const submitting = ref(false)
const error = ref('')

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await auth.login(form.email, form.password)
    router.push(route.query.redirect || '/book')
  } catch (err) {
    error.value =
      err.response?.data?.detail ||
      'Invalid email or password. If you just signed up, check your email for an activation link first.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-md px-4 py-16 sm:px-6">
      <h1 class="text-center font-[Georgia] text-3xl font-bold text-navy-900">Log In</h1>

      <form class="mt-8 space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-6" @submit.prevent="submit">
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
          <label class="mb-1 block text-sm text-slate-600">Password</label>
          <input
            v-model="form.password"
            type="password"
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
          {{ submitting ? 'Logging in...' : 'Log In' }}
        </button>
        <p class="text-center text-sm text-slate-500">
          <RouterLink to="/forgot-password" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500">
            Forgot password?
          </RouterLink>
        </p>
        <p class="text-center text-sm text-slate-500">
          No account?
          <RouterLink to="/register" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500">Sign up</RouterLink>
        </p>
      </form>
    </div>
  </div>
</template>
