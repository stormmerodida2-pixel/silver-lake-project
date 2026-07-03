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
  <div class="mx-auto max-w-md px-4 py-16 sm:px-6">
    <h1 class="text-center font-[Georgia] text-3xl font-bold text-white">Log In</h1>

    <form class="mt-8 space-y-4 rounded-xl border border-navy-800 bg-navy-900 p-6" @submit.prevent="submit">
      <div>
        <label class="mb-1 block text-sm text-slate-300">Email</label>
        <input
          v-model="form.email"
          type="email"
          required
          class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm text-slate-300">Password</label>
        <input
          v-model="form.password"
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
        {{ submitting ? 'Logging in...' : 'Log In' }}
      </button>
      <p class="text-center text-sm text-slate-400">
        <RouterLink to="/forgot-password" class="font-semibold text-gold-400 hover:text-gold-300">
          Forgot password?
        </RouterLink>
      </p>
      <p class="text-center text-sm text-slate-400">
        No account?
        <RouterLink to="/register" class="font-semibold text-gold-400 hover:text-gold-300">Sign up</RouterLink>
      </p>
    </form>
  </div>
</template>
