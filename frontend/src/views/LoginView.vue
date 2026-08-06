<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PasswordInput from '../components/PasswordInput.vue'
import SilverLakeLogo from '../components/SilverLakeLogo.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const form = reactive({ email: '', password: '' })
const submitting = ref(false)
const error = ref('')
// Set only once the password step succeeds for a 2FA-enabled staff account - switches the form
// over to the code-entry step (see submitCode() below) instead of navigating away immediately.
const twoFactorUserId = ref(null)
const otpCode = ref('')
const resendState = ref('idle') // idle -> sending -> sent

function redirectAfterLogin() {
  if (auth.user?.is_staff) {
    router.push('/admin')
  } else if (auth.user?.is_driver) {
    router.push('/driver')
  } else {
    router.push(route.query.redirect || '/')
  }
}

async function submit() {
  submitting.value = true
  error.value = ''
  resendState.value = 'idle'
  try {
    const result = await auth.login(form.email, form.password)
    if (result.two_factor_required) {
      twoFactorUserId.value = result.user_id
      return
    }
    redirectAfterLogin()
  } catch (err) {
    error.value =
      err.response?.data?.detail ||
      'Invalid email or password. If you just signed up, check your email for an activation link first.'
  } finally {
    submitting.value = false
  }
}

async function resendActivationEmail() {
  if (!form.email) {
    error.value = 'Enter your email above first, then resend the activation email.'
    return
  }
  resendState.value = 'sending'
  try {
    await auth.resendActivation(form.email)
  } finally {
    resendState.value = 'sent'
  }
}

async function submitCode() {
  submitting.value = true
  error.value = ''
  try {
    await auth.verifyTwoFactorLogin(twoFactorUserId.value, otpCode.value)
    redirectAfterLogin()
  } catch (err) {
    error.value = err.response?.data?.detail || 'Invalid or expired code.'
  } finally {
    submitting.value = false
  }
}

function backToLogin() {
  twoFactorUserId.value = null
  otpCode.value = ''
  error.value = ''
}
</script>

<template>
  <div class="bg-page">
    <div class="mx-auto max-w-lg px-4 py-16 sm:px-6">
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

      <form
        v-if="!twoFactorUserId"
        class="mt-8 space-y-5 rounded-xl border border-border-subtle bg-surface p-8"
        @submit.prevent="submit"
      >
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
          <label class="mb-1 block text-sm text-foreground-muted">Password</label>
          <PasswordInput
            v-model="form.password"
            required
            input-class="w-full rounded-md border border-border bg-surface-2 px-4 py-3 text-foreground focus:border-accent-border focus:outline-none"
          />
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
        <button
          type="submit"
          :disabled="submitting"
          class="w-full rounded-md bg-accent-bg px-4 py-3 font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
        >
          {{ submitting ? 'Logging in...' : 'Log In' }}
        </button>
        <p class="text-center text-sm text-foreground-muted">
          <RouterLink to="/forgot-password" class="font-semibold text-accent hover:text-accent-strong">
            Forgot password?
          </RouterLink>
        </p>
        <p class="text-center text-sm text-foreground-muted">
          <template v-if="resendState === 'sent'">Activation email sent - check your inbox.</template>
          <template v-else>
            Account not activated?
            <button
              type="button"
              class="font-semibold text-accent hover:text-accent-strong disabled:opacity-60"
              :disabled="resendState === 'sending'"
              @click="resendActivationEmail"
            >
              {{ resendState === 'sending' ? 'Sending...' : 'Resend activation email' }}
            </button>
          </template>
        </p>
        <p class="text-center text-sm text-foreground-muted">
          No account?
          <RouterLink to="/register" class="font-semibold text-accent hover:text-accent-strong"
            >Sign up</RouterLink
          >
        </p>
      </form>

      <form
        v-else
        class="mt-8 space-y-5 rounded-xl border border-border-subtle bg-surface p-8"
        @submit.prevent="submitCode"
      >
        <div>
          <p class="text-sm text-foreground-muted">
            We've emailed a 6-digit code to your address. Enter it below to finish logging in.
          </p>
          <label class="mb-1 mt-4 block text-sm text-foreground-muted">Verification code</label>
          <input
            v-model="otpCode"
            type="text"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="6"
            required
            autofocus
            class="w-full rounded-md border border-border bg-surface-2 px-4 py-3 text-center text-2xl tracking-[0.5em] text-foreground focus:border-accent-border focus:outline-none"
          />
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
        <button
          type="submit"
          :disabled="submitting"
          class="w-full rounded-md bg-accent-bg px-4 py-3 font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
        >
          {{ submitting ? 'Verifying...' : 'Verify & Log In' }}
        </button>
        <button
          type="button"
          class="w-full text-center text-sm font-semibold text-accent hover:text-accent-strong"
          @click="backToLogin"
        >
          Back to login
        </button>
      </form>
    </div>
  </div>
</template>
