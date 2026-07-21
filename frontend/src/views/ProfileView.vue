<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import Swal from 'sweetalert2'

import apiClient from '../api/client'
import PhoneInput from '../components/PhoneInput.vue'
import { useAuthStore } from '../stores/auth'
import { confirmDialog } from '../utils/dialogs'

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
  event.target.value = ''  // allow re-selecting the same file later
  if (!file) return
  avatarError.value = ''
  avatarUploading.value = true
  try {
    const payload = new FormData()
    payload.append('avatar', file)
    const { data } = await apiClient.post('/auth/me/avatar/', payload)
    avatarUrl.value = data.avatar
    await auth.refreshProfile()  // keeps the NavBar's copy (and localStorage) in sync too
  } catch (err) {
    const detail = err?.response?.data
    avatarError.value = typeof detail === 'object'
      ? Object.values(detail).flat().join(' ')
      : 'Could not upload this photo.'
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
  } catch (err) {
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
  setTimeout(() => { copied.value = false }, 2000)
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
  } catch (err) {
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
    await auth.refreshProfile()  // keeps the NavBar's cached name (and localStorage) in sync too
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
  <div class="bg-white">
    <div class="mx-auto max-w-2xl px-4 py-16 sm:px-6 lg:py-20">
      <h1 class="text-center font-[Georgia] text-4xl font-bold text-navy-900">My Profile</h1>
      <p class="mt-3 text-center text-base text-slate-500">Update your name and contact details.</p>

      <p v-if="loading" class="mt-10 text-center text-slate-500">Loading...</p>

      <template v-else>
        <!-- Profile photo -->
        <div class="mt-10 flex flex-col items-center gap-4 rounded-2xl border border-slate-200 bg-slate-50 p-8 sm:flex-row sm:p-10">
          <div class="h-24 w-24 shrink-0 overflow-hidden rounded-full border-2 border-white bg-navy-900 shadow-sm">
            <img v-if="avatarUrl" :src="avatarUrl" alt="Your profile photo" class="h-full w-full object-cover" />
            <div v-else class="flex h-full w-full items-center justify-center font-[Georgia] text-2xl font-bold text-gold-400">
              {{ initials || '—' }}
            </div>
          </div>
          <div class="flex-1 text-center sm:text-left">
            <p class="font-[Georgia] text-lg font-bold text-navy-900">Profile Photo</p>
            <p class="mt-1 text-sm text-slate-500">JPG or PNG, up to 5MB.</p>
            <p v-if="avatarError" class="mt-2 text-sm text-red-600">{{ avatarError }}</p>
            <input ref="avatarInput" type="file" accept="image/*" class="hidden" @change="onAvatarSelected" />
            <div class="mt-3 flex flex-wrap justify-center gap-3 sm:justify-start">
              <button
                type="button"
                :disabled="avatarUploading"
                class="rounded-lg bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
                @click="pickAvatar"
              >
                {{ avatarUploading ? 'Saving…' : (avatarUrl ? 'Change Photo' : 'Upload Photo') }}
              </button>
              <button
                v-if="avatarUrl"
                type="button"
                :disabled="avatarUploading"
                class="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-600 transition hover:border-red-400 hover:text-red-600 disabled:opacity-60"
                @click="removeAvatar"
              >
                Remove
              </button>
            </div>
          </div>
        </div>

        <!-- Loyalty -->
        <div v-if="loyaltyTierName || nextLoyaltyTierName" class="mt-6 rounded-2xl border border-navy-800 bg-navy-900 p-8 sm:p-10">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p class="font-[Georgia] text-lg font-bold text-white">
                {{ loyaltyTierName ? `${loyaltyTierName} Member` : 'Loyalty Program' }}
              </p>
              <p class="mt-1 max-w-md text-sm text-slate-300">
                <template v-if="loyaltyTierName && Number(loyaltyDiscountPercent) > 0">
                  You get {{ Number(loyaltyDiscountPercent) }}% off every booking, automatically - no code needed.
                </template>
                <template v-else>
                  Complete more trips to unlock an automatic discount on every future booking.
                </template>
              </p>
              <p v-if="nextLoyaltyTierName" class="mt-2 text-xs font-semibold uppercase tracking-wide text-gold-400">
                {{ tripsToNextLoyaltyTier }} more trip{{ tripsToNextLoyaltyTier === 1 ? '' : 's' }} to {{ nextLoyaltyTierName }}
              </p>
              <p v-else class="mt-2 text-xs font-semibold uppercase tracking-wide text-gold-400">
                You've reached the top tier
              </p>
            </div>
            <div class="rounded-lg border border-gold-500/40 bg-gold-500/10 px-4 py-2 text-center">
              <p class="font-[Georgia] text-2xl font-bold text-gold-400">{{ completedTripCount }}</p>
              <p class="text-xs font-medium uppercase tracking-wide text-slate-400">Completed Trips</p>
            </div>
          </div>
        </div>

        <!-- Referrals -->
        <div class="mt-6 rounded-2xl border border-navy-800 bg-navy-900 p-8 sm:p-10">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p class="font-[Georgia] text-lg font-bold text-white">
                Give KES {{ Number(referralCreditAmount).toLocaleString() }}, Get KES {{ Number(referralCreditAmount).toLocaleString() }}
              </p>
              <p class="mt-1 max-w-md text-sm text-slate-300">
                Share your code - once a friend's first trip is confirmed, you earn KES
                {{ Number(referralCreditAmount).toLocaleString() }} in credit toward your own next booking.
              </p>
            </div>
            <div class="rounded-lg border border-gold-500/40 bg-gold-500/10 px-4 py-2 text-center">
              <p class="font-[Georgia] text-2xl font-bold text-gold-400">KES {{ Number(referralCreditBalance).toLocaleString() }}</p>
              <p class="text-xs font-medium uppercase tracking-wide text-slate-400">Available Credit</p>
            </div>
          </div>

          <div class="mt-5 flex flex-wrap items-center gap-3">
            <span class="rounded-md bg-navy-800 px-4 py-2 font-mono text-lg font-bold tracking-widest text-gold-400">
              {{ referralCode }}
            </span>
            <button
              type="button"
              class="rounded-md bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition hover:bg-gold-400"
              @click="copyReferralLink"
            >
              {{ copied ? 'Link Copied!' : 'Copy Referral Link' }}
            </button>
          </div>
        </div>

      <form class="mt-6 space-y-6 rounded-2xl border border-slate-200 bg-slate-50 p-8 sm:p-10" @submit.prevent="submit">
        <div class="grid gap-5 sm:grid-cols-2">
          <div>
            <label class="mb-1.5 block text-sm font-medium text-slate-600">First name</label>
            <input
              v-model="form.first_name"
              type="text"
              required
              class="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-base text-navy-900 focus:border-brand-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-sm font-medium text-slate-600">Last name</label>
            <input
              v-model="form.last_name"
              type="text"
              class="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-base text-navy-900 focus:border-brand-blue-500 focus:outline-none"
            />
          </div>
        </div>

        <div>
          <label class="mb-1.5 block text-sm font-medium text-slate-600">Phone number</label>
          <PhoneInput v-model="form.phone_number" />
        </div>

        <div>
          <label class="mb-1.5 block text-sm font-medium text-slate-600">Email</label>
          <input
            :value="email"
            type="email"
            disabled
            class="w-full cursor-not-allowed rounded-lg border border-slate-200 bg-slate-100 px-4 py-3 text-base text-slate-500"
          />
          <p class="mt-1.5 text-xs text-slate-400">Your email is also your login - contact us if you need it changed.</p>
        </div>

        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>

        <button
          type="submit"
          :disabled="submitting"
          class="w-full rounded-lg bg-gold-500 px-4 py-3 text-base font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
        >
          {{ submitting ? 'Saving...' : 'Save Changes' }}
        </button>
      </form>
      </template>

      <p class="mt-6 text-center text-sm text-slate-500">
        Want to change your password instead?
        <RouterLink to="/account/change-password" class="font-semibold text-brand-blue-600 hover:underline">
          Change Password
        </RouterLink>
      </p>
    </div>
  </div>
</template>
