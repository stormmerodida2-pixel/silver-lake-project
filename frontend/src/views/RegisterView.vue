<script setup>
import { reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import PasswordInput from '../components/PasswordInput.vue'
import PhoneInput from '../components/PhoneInput.vue'
import SilverLakeLogo from '../components/SilverLakeLogo.vue'
import { useAuthStore } from '../stores/auth'
import { trackEvent } from '../utils/analytics'

const auth = useAuthStore()
const route = useRoute()

// Prefills from a shared referral link (e.g. .../register?ref=ABC12345) - still editable, so
// someone who was given a code verbally can type it in just as easily.
const form = reactive({
  firstName: '', lastName: '', email: '', phoneNumber: '', password: '',
  referralCode: typeof route.query.ref === 'string' ? route.query.ref.toUpperCase() : '',
})
const agreedToTerms = ref(false)
const submitting = ref(false)
const error = ref('')
const submitted = ref(false)

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await auth.register(form)
    submitted.value = true
    trackEvent('sign_up', { method: 'email' })
  } catch (err) {
    const data = err.response?.data
    error.value = data ? Object.values(data).flat().join(' ') : 'Could not create your account.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-lg px-4 py-16 sm:px-6">
      <RouterLink to="/" class="flex justify-center">
        <SilverLakeLogo :size="48" />
      </RouterLink>
      <h1 class="mt-4 text-center font-[Georgia] text-3xl font-bold text-navy-900">Create Account</h1>

      <div v-if="submitted" class="mt-8 rounded-xl border border-slate-200 bg-slate-50 p-8 text-center">
        <h2 class="font-[Georgia] text-xl font-bold text-brand-blue-600">Check your email</h2>
        <p class="mt-2 text-sm text-slate-600">
          We've sent an activation link to {{ form.email }}. Click it to activate your account, then log in.
        </p>
        <RouterLink to="/login" class="mt-4 inline-block font-semibold text-brand-blue-600 hover:text-brand-blue-500">
          Go to Log In
        </RouterLink>
      </div>

      <form v-else class="mt-8 space-y-5 rounded-xl border border-slate-200 bg-slate-50 p-8" @submit.prevent="submit">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1 block text-sm text-slate-600">First name</label>
            <input
              v-model="form.firstName"
              type="text"
              required
              class="w-full rounded-md border border-slate-300 bg-white px-4 py-3 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label class="mb-1 block text-sm text-slate-600">Last name</label>
            <input
              v-model="form.lastName"
              type="text"
              required
              class="w-full rounded-md border border-slate-300 bg-white px-4 py-3 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
            />
          </div>
        </div>
        <div>
          <label class="mb-1 block text-sm text-slate-600">Email</label>
          <input
            v-model="form.email"
            type="email"
            required
            class="w-full rounded-md border border-slate-300 bg-white px-4 py-3 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm text-slate-600">Phone (M-Pesa number)</label>
          <PhoneInput v-model="form.phoneNumber" required />
        </div>
        <div>
          <label class="mb-1 block text-sm text-slate-600">Password</label>
          <PasswordInput
            v-model="form.password"
            required
            input-class="w-full rounded-md border border-slate-300 bg-white px-4 py-3 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm text-slate-600">Referral code (optional)</label>
          <input
            v-model="form.referralCode"
            type="text"
            placeholder="e.g. AB12CD34"
            class="w-full rounded-md border border-slate-300 bg-white px-4 py-3 uppercase text-navy-900 placeholder:normal-case focus:border-brand-blue-500 focus:outline-none"
          />
          <p class="mt-1 text-xs text-slate-500">Got a code from a friend? Enter it here and they'll earn referral credit.</p>
        </div>
        <div v-if="error" class="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <svg class="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          <span>{{ error }}</span>
        </div>
        <label class="flex items-start gap-2.5 text-sm text-slate-600">
          <input
            v-model="agreedToTerms"
            type="checkbox"
            required
            class="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-brand-blue-600 focus:ring-brand-blue-500"
          />
          <span>
            I agree to the
            <RouterLink to="/terms" target="_blank" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500">Terms of Service</RouterLink>
            and
            <RouterLink to="/privacy" target="_blank" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500">Privacy Policy</RouterLink>.
          </span>
        </label>
        <button
          type="submit"
          :disabled="submitting || !agreedToTerms"
          class="w-full rounded-md bg-gold-500 px-4 py-3 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
        >
          {{ submitting ? 'Creating account...' : 'Sign Up' }}
        </button>
        <p class="text-center text-sm text-slate-500">
          Already have an account?
          <RouterLink to="/login" class="font-semibold text-brand-blue-600 hover:text-brand-blue-500">Log in</RouterLink>
        </p>
      </form>
    </div>
  </div>
</template>
