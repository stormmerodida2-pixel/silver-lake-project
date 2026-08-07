<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import Swal from 'sweetalert2'

import apiClient from '../api/client'
import PhoneInput from '../components/PhoneInput.vue'
import { useAuthStore } from '../stores/auth'
import { confirmDialog, promptDialog } from '../utils/dialogs'

const auth = useAuthStore()
const router = useRouter()

const form = reactive({ first_name: '', last_name: '', phone_number: '' })
const email = ref('')
const loading = ref(true)
const submitting = ref(false)
const error = ref('')

// ── Profile photo ────────────────────────────────────────────────────────────
const avatarUrl = ref(null)
const avatarInput = ref(null)
const avatarUploading = ref(false)
const avatarError = ref('')
const initials = computed(() => {
  const name = `${form.first_name || ''} ${form.last_name || ''}`.trim()
  const parts = name.split(/\s+/).filter(Boolean)
  return (parts[0]?.[0] || '') + (parts[1]?.[0] || '')
})

function pickAvatar() {
  avatarInput.value?.click()
}

async function onAvatarSelected(event) {
  const file = event.target.files[0]
  event.target.value = '' // allow re-selecting the same file later
  if (!file) return
  avatarError.value = ''
  avatarUploading.value = true
  try {
    const payload = new FormData()
    payload.append('avatar', file)
    const { data } = await apiClient.post('/auth/me/avatar/', payload)
    avatarUrl.value = data.avatar
    await auth.refreshProfile() // keeps the NavBar's copy (and localStorage) in sync too
  } catch (err) {
    const detail = err?.response?.data
    avatarError.value =
      typeof detail === 'object' ? Object.values(detail).flat().join(' ') : 'Could not upload this photo.'
  } finally {
    avatarUploading.value = false
  }
}

async function removeAvatar() {
  if (!(await confirmDialog('Remove your profile photo?'))) return
  avatarError.value = ''
  avatarUploading.value = true
  try {
    const { data } = await apiClient.delete('/auth/me/avatar/')
    avatarUrl.value = data.avatar
    await auth.refreshProfile()
  } catch {
    avatarError.value = 'Could not remove your photo.'
  } finally {
    avatarUploading.value = false
  }
}

// ── Loyalty ───────────────────────────────────────────────────────────────────
const loyaltyTierName = ref(null)
const loyaltyDiscountPercent = ref(0)
const completedTripCount = ref(0)
const nextLoyaltyTierName = ref(null)
const tripsToNextLoyaltyTier = ref(null)

// ── Referrals ────────────────────────────────────────────────────────────────
const referralCode = ref('')
const referralCreditBalance = ref(0)
const referralCreditAmount = ref(0)
const referralLink = computed(() => `${window.location.origin}/register?ref=${referralCode.value}`)
const copied = ref(false)

async function copyReferralLink() {
  await navigator.clipboard.writeText(referralLink.value)
  copied.value = true
  setTimeout(() => {
    copied.value = false
  }, 2000)
}

// ── Two-factor authentication (staff/admin accounts only) ─────────────────────
const twoFactorEnabled = ref(false)
const twoFactorBusy = ref(false)
const twoFactorError = ref('')

async function enableTwoFactor() {
  if (
    !(await confirmDialog(
      "You'll need to enter a code emailed to you every time you log in from now on. Enable two-factor authentication?",
    ))
  )
    return
  twoFactorError.value = ''
  twoFactorBusy.value = true
  try {
    await apiClient.post('/auth/2fa/enable/')
    twoFactorEnabled.value = true
  } catch {
    twoFactorError.value = 'Could not enable two-factor authentication.'
  } finally {
    twoFactorBusy.value = false
  }
}

async function disableTwoFactor() {
  const password = await promptDialog('Enter your current password to confirm:', { inputType: 'password' })
  if (password === null) return
  twoFactorError.value = ''
  twoFactorBusy.value = true
  try {
    await apiClient.post('/auth/2fa/disable/', { password })
    twoFactorEnabled.value = false
  } catch (err) {
    twoFactorError.value = err.response?.data?.password?.[0] || 'Could not disable two-factor authentication.'
  } finally {
    twoFactorBusy.value = false
  }
}

async function loadProfile() {
  loading.value = true
  try {
    const { data } = await apiClient.get('/auth/me/')
    form.first_name = data.first_name
    form.last_name = data.last_name
    form.phone_number = data.phone_number
    email.value = data.email
    avatarUrl.value = data.avatar
    referralCode.value = data.referral_code
    referralCreditBalance.value = data.referral_credit_balance
    referralCreditAmount.value = data.referral_credit_amount
    loyaltyTierName.value = data.loyalty_tier_name
    loyaltyDiscountPercent.value = data.loyalty_discount_percent
    completedTripCount.value = data.completed_trip_count
    nextLoyaltyTierName.value = data.next_loyalty_tier_name
    tripsToNextLoyaltyTier.value = data.trips_to_next_loyalty_tier
    twoFactorEnabled.value = data.two_factor_enabled
  } catch {
    error.value = 'Could not load your profile.'
  } finally {
    loading.value = false
  }
}

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    const { data } = await apiClient.patch('/auth/me/', form)
    form.first_name = data.first_name
    form.last_name = data.last_name
    form.phone_number = data.phone_number
    await auth.refreshProfile() // keeps the NavBar's cached name (and localStorage) in sync too
    await Swal.fire({
      icon: 'success',
      title: 'Profile updated!',
      text: 'Your changes have been saved.',
      confirmButtonColor: '#eab308',
    })
    router.push(auth.user?.is_staff ? '/admin' : '/')
  } catch (err) {
    const data = err.response?.data
    error.value = data ? Object.values(data).flat().join(' ') : 'Could not update your profile.'
  } finally {
    submitting.value = false
  }
}

onMounted(loadProfile)
</script>

<template>
  <div class="bg-page">
    <div class="mx-auto max-w-2xl px-4 py-16 sm:px-6 lg:py-20">
      <h1 class="text-center font-[Georgia] text-4xl font-bold text-foreground">My Profile</h1>
      <p class="mt-3 text-center text-base text-foreground-subtle">Update your name and contact details.</p>

      <p v-if="loading" class="mt-10 text-center text-foreground-subtle">Loading...</p>

      <template v-else>
        <!-- Profile photo -->
        <div
          class="mt-10 flex flex-col items-center gap-4 rounded-2xl border border-border-subtle bg-surface p-8 sm:flex-row sm:p-10"
        >
          <div class="h-24 w-24 shrink-0 overflow-hidden rounded-full border-2 border-border-subtle bg-surface shadow-sm">
            <img v-if="avatarUrl" :src="avatarUrl" alt="Your profile photo" class="h-full w-full object-cover" />
            <div
              v-else
              class="flex h-full w-full items-center justify-center font-[Georgia] text-2xl font-bold text-accent"
            >
              {{ initials || '—' }}
            </div>
          </div>
          <div class="flex-1 text-center sm:text-left">
            <p class="font-[Georgia] text-lg font-bold text-foreground">Profile Photo</p>
            <p class="mt-1 text-sm text-foreground-subtle">JPG or PNG, up to 5MB.</p>
            <p v-if="avatarError" class="mt-2 text-sm text-danger">{{ avatarError }}</p>
            <input ref="avatarInput" type="file" accept="image/*" class="hidden" @change="onAvatarSelected" />
            <div class="mt-3 flex flex-wrap justify-center gap-3 sm:justify-start">
              <button
                type="button"
                :disabled="avatarUploading"
                class="rounded-lg bg-accent-bg px-4 py-2 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
                @click="pickAvatar"
              >
                {{ avatarUploading ? 'Saving…' : avatarUrl ? 'Change Photo' : 'Upload Photo' }}
              </button>
              <button
                v-if="avatarUrl"
                type="button"
                :disabled="avatarUploading"
                class="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-foreground-secondary transition hover:border-danger-border hover:text-danger disabled:opacity-60"
                @click="removeAvatar"
              >
                Remove
              </button>
            </div>
          </div>
        </div>

        <!-- Loyalty -->
        <div
          v-if="loyaltyTierName || nextLoyaltyTierName"
          class="mt-6 rounded-2xl border border-border-subtle bg-surface p-8 sm:p-10"
        >
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p class="font-[Georgia] text-lg font-bold text-foreground">
                {{ loyaltyTierName ? `${loyaltyTierName} Member` : 'Loyalty Program' }}
              </p>
              <p class="mt-1 max-w-md text-sm text-foreground-secondary">
                <template v-if="loyaltyTierName && Number(loyaltyDiscountPercent) > 0">
                  You get {{ Number(loyaltyDiscountPercent) }}% off every booking, automatically - no code needed.
                </template>
                <template v-else>
                  Complete more trips to unlock an automatic discount on every future booking.
                </template>
              </p>
              <p v-if="nextLoyaltyTierName" class="mt-2 text-xs font-semibold uppercase tracking-wide text-accent">
                {{ tripsToNextLoyaltyTier }} more trip{{ tripsToNextLoyaltyTier === 1 ? '' : 's' }} to
                {{ nextLoyaltyTierName }}
              </p>
              <p v-else class="mt-2 text-xs font-semibold uppercase tracking-wide text-accent">
                You've reached the top tier
              </p>
            </div>
            <div class="rounded-lg border border-accent-border-strong/40 bg-accent-bg/10 px-4 py-2 text-center">
              <p class="font-[Georgia] text-2xl font-bold text-accent">{{ completedTripCount }}</p>
              <p class="text-xs font-medium uppercase tracking-wide text-foreground-muted">Completed Trips</p>
            </div>
          </div>
        </div>

        <!-- Referrals -->
        <div class="mt-6 rounded-2xl border border-border-subtle bg-surface p-8 sm:p-10">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p class="font-[Georgia] text-lg font-bold text-foreground">
                Give KES {{ Number(referralCreditAmount).toLocaleString() }}, Get KES
                {{ Number(referralCreditAmount).toLocaleString() }}
              </p>
              <p class="mt-1 max-w-md text-sm text-foreground-secondary">
                Share your code - once a friend's first trip is confirmed, you earn KES
                {{ Number(referralCreditAmount).toLocaleString() }} in credit toward your own next booking.
              </p>
            </div>
            <div class="rounded-lg border border-accent-border-strong/40 bg-accent-bg/10 px-4 py-2 text-center">
              <p class="font-[Georgia] text-2xl font-bold text-accent">
                KES {{ Number(referralCreditBalance).toLocaleString() }}
              </p>
              <p class="text-xs font-medium uppercase tracking-wide text-foreground-muted">Available Credit</p>
            </div>
          </div>

          <div class="mt-5 flex flex-wrap items-center gap-3">
            <span class="rounded-md bg-surface-2 px-4 py-2 font-mono text-lg font-bold tracking-widest text-accent">
              {{ referralCode }}
            </span>
            <button
              type="button"
              class="rounded-md bg-accent-bg px-4 py-2 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover"
              @click="copyReferralLink"
            >
              {{ copied ? 'Link Copied!' : 'Copy Referral Link' }}
            </button>
          </div>
        </div>

        <!-- Security (staff/admin accounts only) -->
        <div v-if="auth.user?.is_staff" class="mt-6 rounded-2xl border border-border-subtle bg-surface p-8 sm:p-10">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p class="font-[Georgia] text-lg font-bold text-foreground">Two-Factor Authentication</p>
              <p class="mt-1 max-w-md text-sm text-foreground-secondary">
                <template v-if="twoFactorEnabled"> Enabled - a code is emailed to you every time you log in. </template>
                <template v-else>
                  Adds a second step at login (a code emailed to you) - recommended for staff and admin accounts, since
                  they can move money and manage users.
                </template>
              </p>
            </div>
            <span
              class="shrink-0 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide"
              :class="twoFactorEnabled ? 'bg-emerald-500/10 text-success' : 'bg-surface-2 text-foreground-muted'"
            >
              {{ twoFactorEnabled ? 'Enabled' : 'Disabled' }}
            </span>
          </div>
          <p v-if="twoFactorError" class="mt-3 text-sm text-danger">{{ twoFactorError }}</p>
          <button
            v-if="!twoFactorEnabled"
            type="button"
            :disabled="twoFactorBusy"
            class="mt-5 rounded-md bg-accent-bg px-4 py-2 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
            @click="enableTwoFactor"
          >
            {{ twoFactorBusy ? 'Enabling...' : 'Enable Two-Factor Authentication' }}
          </button>
          <button
            v-else
            type="button"
            :disabled="twoFactorBusy"
            class="mt-5 rounded-md border border-red-500/40 px-4 py-2 text-sm font-semibold text-danger transition hover:bg-red-500/10 disabled:opacity-60"
            @click="disableTwoFactor"
          >
            {{ twoFactorBusy ? 'Disabling...' : 'Disable Two-Factor Authentication' }}
          </button>
        </div>

        <form
          class="mt-6 space-y-6 rounded-2xl border border-border-subtle bg-surface p-8 sm:p-10"
          @submit.prevent="submit"
        >
          <div class="grid gap-5 sm:grid-cols-2">
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground-muted">First name</label>
              <input
                v-model="form.first_name"
                type="text"
                required
                class="w-full rounded-lg border border-border bg-surface-2 px-4 py-3 text-base text-foreground focus:border-accent-border focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground-muted">Last name</label>
              <input
                v-model="form.last_name"
                type="text"
                class="w-full rounded-lg border border-border bg-surface-2 px-4 py-3 text-base text-foreground focus:border-accent-border focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label class="mb-1.5 block text-sm font-medium text-foreground-muted">Phone number</label>
            <PhoneInput v-model="form.phone_number" />
          </div>

          <div>
            <label class="mb-1.5 block text-sm font-medium text-foreground-muted">Email</label>
            <input
              :value="email"
              type="email"
              disabled
              class="w-full cursor-not-allowed rounded-lg border border-border-subtle bg-surface-2 px-4 py-3 text-base text-foreground-subtle"
            />
            <p class="mt-1.5 text-xs text-foreground-muted">
              Your email is also your login - contact us if you need it changed.
            </p>
          </div>

          <p v-if="error" class="text-sm text-danger">{{ error }}</p>

          <button
            type="submit"
            :disabled="submitting"
            class="w-full rounded-lg bg-accent-bg px-4 py-3 text-base font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
          >
            {{ submitting ? 'Saving...' : 'Save Changes' }}
          </button>
        </form>
      </template>

      <p class="mt-6 text-center text-sm text-foreground-subtle">
        Want to change your password instead?
        <RouterLink to="/account/change-password" class="font-semibold text-accent hover:underline">
          Change Password
        </RouterLink>
      </p>
    </div>
  </div>
</template>
