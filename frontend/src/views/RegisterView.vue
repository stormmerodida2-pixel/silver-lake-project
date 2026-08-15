<script setup>
import { reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import AuthLayout from '../components/AuthLayout.vue'
import PasswordInput from '../components/PasswordInput.vue'
import PhoneInput from '../components/PhoneInput.vue'
import { useAuthStore } from '../stores/auth'
import { trackEvent } from '../utils/analytics'

const auth = useAuthStore()
const route = useRoute()

// Prefills from a shared referral link (e.g. .../register?ref=ABC12345) - still editable, so
// someone who was given a code verbally can type it in just as easily.
const form = reactive({
  firstName: '',
  lastName: '',
  email: '',
  phoneNumber: '',
  password: '',
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
  <AuthLayout>
    <div v-if="submitted" class="rounded-xl border border-border-subtle bg-surface p-8 text-center">
      <h2 class="font-[Georgia] text-xl font-bold text-success">Check your email</h2>
      <p class="mt-2 text-sm text-foreground-muted">
        We've sent an activation link to {{ form.email }}. Click it to activate your account, then log in.
      </p>
      <RouterLink to="/login" class="mt-4 inline-block font-semibold text-accent hover:text-accent-strong">
        Go to Log In
      </RouterLink>
    </div>

    <template v-else>
      <h1 class="font-[Georgia] text-2xl font-bold text-foreground">Create your account</h1>
      <p class="mt-1 text-sm text-foreground-muted">Book with a driver or self-drive, your way.</p>

      <form class="mt-6 space-y-5 rounded-xl border border-border-subtle bg-surface p-8" @submit.prevent="submit">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1 block text-sm text-foreground-muted">First name</label>
            <input
              v-model="form.firstName"
              type="text"
              required
              class="w-full rounded-md border border-border bg-surface-2 px-4 py-3 text-foreground focus:border-accent-border focus:outline-none"
            />
          </div>
          <div>
            <label class="mb-1 block text-sm text-foreground-muted">Last name</label>
            <input
              v-model="form.lastName"
              type="text"
              required
              class="w-full rounded-md border border-border bg-surface-2 px-4 py-3 text-foreground focus:border-accent-border focus:outline-none"
            />
          </div>
        </div>
        <div>
          <label class="mb-1 block text-sm text-foreground-muted">Email</label>
          <input
            v-model="form.email"
            type="email"
            required
            class="w-full rounded-md border border-border bg-surface-2 px-4 py-3 text-foreground focus:border-accent-border focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm text-foreground-muted">Phone (M-Pesa number)</label>
          <PhoneInput v-model="form.phoneNumber" required />
        </div>
        <div>
          <label class="mb-1 block text-sm text-foreground-muted">Password</label>
          <PasswordInput
            v-model="form.password"
            required
            input-class="w-full rounded-md border border-border bg-surface-2 px-4 py-3 text-foreground focus:border-accent-border focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm text-foreground-muted">Referral code (optional)</label>
          <input
            v-model="form.referralCode"
            type="text"
            placeholder="e.g. AB12CD34"
            class="w-full rounded-md border border-border bg-surface-2 px-4 py-3 uppercase text-foreground placeholder:normal-case focus:border-accent-border focus:outline-none"
          />
          <p class="mt-1 text-xs text-foreground-muted">
            Got a code from a friend? Enter it here and they'll earn referral credit.
          </p>
        </div>
        <div
          v-if="error"
          class="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-danger"
        >
          <svg class="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
            />
          </svg>
          <span>{{ error }}</span>
        </div>
        <label class="flex items-start gap-2.5 text-sm text-foreground-muted">
          <input
            v-model="agreedToTerms"
            type="checkbox"
            required
            class="mt-0.5 h-4 w-4 shrink-0 rounded border-border text-accent-strong focus:ring-accent-border-strong"
          />
          <span>
            I agree to the
            <RouterLink to="/terms" target="_blank" class="font-semibold text-accent hover:text-accent-strong"
              >Terms of Service</RouterLink
            >
            and
            <RouterLink
              to="/privacy"
              target="_blank"
              class="font-semibold text-accent hover:text-accent-strong"
              >Privacy Policy</RouterLink
            >.
          </span>
        </label>
        <button
          type="submit"
          :disabled="submitting || !agreedToTerms"
          class="w-full rounded-md bg-accent-bg px-4 py-3 font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
        >
          {{ submitting ? 'Creating account...' : 'Sign Up' }}
        </button>
        <p class="text-center text-sm text-foreground-muted">
          Already have an account?
          <RouterLink to="/login" class="font-semibold text-accent hover:text-accent-strong"
            >Log in</RouterLink
          >
        </p>
      </form>
    </template>
  </AuthLayout>
</template>
