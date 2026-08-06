<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import apiClient from '../api/client'
import PhoneInput from '../components/PhoneInput.vue'

const route = useRoute()

// Temporary, easily-reversible: flip back to true once real M-Pesa production credentials are
// in place. Nothing about the M-Pesa flow itself (STK push, callback, polling) is removed -
// it's just not offered as a customer-facing option while this is false, in favor of Bank
// Transfer.
const MPESA_ENABLED = false
const primaryMethod = computed(() => (MPESA_ENABLED ? 'mpesa' : 'bank_transfer'))

const booking = ref(null)
const loading = ref(true)
const loadError = ref('')

const phoneNumber = ref('')
const payOption = ref('deposit') // 'deposit' | 'full'
const paymentMethod = ref(primaryMethod.value) // 'mpesa' | 'cash' | 'bank_transfer'
const submitting = ref(false)
const error = ref('')
const requested = ref(false)
const paymentOutcome = ref(null) // null (waiting) | 'successful' | 'failed' | 'timeout'

const cashAcknowledged = ref(false)
const declaringCash = ref(false)
const cashError = ref('')

const bankTransferAcknowledged = ref(false)
const bankTransferReference = ref('')
const declaringBankTransfer = ref(false)
const bankTransferError = ref('')

const pendingCashPayment = computed(() => {
  if (!booking.value) return null
  return (booking.value.pending_payments || []).find((p) => p.method === 'cash') || null
})
const pendingBankTransferPayment = computed(() => {
  if (!booking.value) return null
  return (booking.value.pending_payments || []).find((p) => p.method === 'bank_transfer') || null
})
// Whichever's actually pending, for the shared "awaiting confirmation" panel below - a booking
// only ever has one at a time in practice (declaring either one is blocked once the balance is
// already reserved by the other).
const pendingOfflinePayment = computed(() => pendingCashPayment.value || pendingBankTransferPayment.value)

// A walk-in booking (created on the spot by a driver) starts Confirmed with nothing paid and
// no deposit requirement at all - full payment is typically only collected once the trip is
// over, so there's no "deposit vs full" choice to make here the way an online booking has.
const isWalkIn = computed(() => booking.value?.source === 'driver_onsite')

async function loadBooking() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await apiClient.get(`/pay/${route.params.token}/`)
    booking.value = data
    if (data.source === 'driver_onsite') payOption.value = 'full'
    paymentMethod.value = primaryMethod.value
  } catch {
    loadError.value = 'This payment link is invalid or has expired.'
  } finally {
    loading.value = false
  }
}

const amountToPay = computed(() => {
  if (!booking.value) return 0
  return payOption.value === 'full' ? Number(booking.value.balance_due) : Number(booking.value.deposit_amount)
})

// ── Payment status polling ──────────────────────────────────────────────────
let pollTimer = null
let pollAttempts = 0
const MAX_POLL_ATTEMPTS = 30 // ~90s at 3s intervals

function stopPolling() {
  clearInterval(pollTimer)
  pollTimer = null
}

function startPolling(paymentId) {
  pollAttempts = 0
  stopPolling()
  pollTimer = setInterval(async () => {
    pollAttempts += 1
    try {
      const { data } = await apiClient.get(`/pay/${route.params.token}/payments/${paymentId}/`)
      if (data.status === 'successful') {
        stopPolling()
        paymentOutcome.value = 'successful'
        loadBooking()
      } else if (data.status === 'failed') {
        stopPolling()
        paymentOutcome.value = 'failed'
      } else if (pollAttempts >= MAX_POLL_ATTEMPTS) {
        stopPolling()
        paymentOutcome.value = 'timeout'
      }
    } catch {
      if (pollAttempts >= MAX_POLL_ATTEMPTS) {
        stopPolling()
        paymentOutcome.value = 'timeout'
      }
    }
  }, 3000)
}

onUnmounted(stopPolling)

async function payWithMpesa() {
  submitting.value = true
  error.value = ''
  try {
    const { data } = await apiClient.post(`/pay/${route.params.token}/stk-push/`, {
      phone_number: phoneNumber.value,
      amount: amountToPay.value,
    })
    paymentOutcome.value = null
    requested.value = true
    startPolling(data.payment_id)
  } catch (err) {
    error.value =
      err.response?.data?.detail ||
      'Could not start M-Pesa payment. You can also pay via Paybill 400400 (Acc: SILVERLAKE).'
  } finally {
    submitting.value = false
  }
}

function retryPayment() {
  paymentOutcome.value = null
  requested.value = false
}

async function declareCash() {
  declaringCash.value = true
  cashError.value = ''
  try {
    await apiClient.post(`/pay/${route.params.token}/declare-cash/`, {
      amount: amountToPay.value,
    })
    await loadBooking()
    cashAcknowledged.value = false
  } catch (err) {
    cashError.value = err.response?.data?.detail || 'Could not record your cash payment. Please try again.'
  } finally {
    declaringCash.value = false
  }
}

async function declareBankTransfer() {
  declaringBankTransfer.value = true
  bankTransferError.value = ''
  try {
    await apiClient.post(`/pay/${route.params.token}/declare-bank-transfer/`, {
      amount: amountToPay.value,
      reference: bankTransferReference.value,
    })
    await loadBooking()
    bankTransferAcknowledged.value = false
    bankTransferReference.value = ''
  } catch (err) {
    bankTransferError.value = err.response?.data?.detail || 'Could not record your bank transfer. Please try again.'
  } finally {
    declaringBankTransfer.value = false
  }
}

onMounted(loadBooking)
</script>

<template>
  <div class="min-h-screen bg-page">
    <div class="mx-auto max-w-lg px-4 py-16 sm:px-6">
      <div class="text-center">
        <h1 class="font-[Georgia] text-2xl font-bold text-foreground">Pay for Your Trip</h1>
        <p class="mt-2 text-sm text-foreground-subtle">SilverLake Car Rentals</p>
      </div>

      <p v-if="loading" class="mt-10 text-center text-foreground-subtle">Loading...</p>
      <div
        v-else-if="loadError"
        class="mt-10 rounded-xl border border-red-500/20 bg-red-500/10 p-6 text-center text-danger"
      >
        {{ loadError }}
      </div>

      <template v-else-if="booking">
        <div class="mt-8 rounded-2xl border border-border-subtle bg-surface p-6">
          <p class="text-sm text-foreground-subtle">Booking for</p>
          <h2 class="font-[Georgia] text-lg font-bold text-foreground">{{ booking.customer_name }}</h2>
          <p class="mt-1 text-sm text-foreground-muted">
            {{ booking.vehicle_name
            }}<span v-if="booking.driver_name"> &middot; Driver: {{ booking.driver_name }}</span>
          </p>
          <p class="text-sm text-foreground-subtle">{{ booking.start_date }} to {{ booking.end_date }}</p>

          <div class="mt-4 space-y-1 border-t border-border-subtle pt-4 text-sm">
            <div class="flex justify-between text-foreground-muted">
              <span>Total</span>
              <span>KES {{ Number(booking.total_amount).toLocaleString() }}</span>
            </div>
            <div class="flex justify-between text-foreground-muted">
              <span>Paid so far</span>
              <span>KES {{ Number(booking.amount_paid).toLocaleString() }}</span>
            </div>
            <div class="flex justify-between text-base font-bold text-foreground">
              <span>Balance Due</span>
              <span class="text-accent-strong">KES {{ Number(booking.balance_due).toLocaleString() }}</span>
            </div>
          </div>
        </div>

        <div
          v-if="booking.status === 'cancelled'"
          class="mt-6 rounded-xl border border-border-subtle bg-surface p-6 text-center text-sm text-foreground-subtle"
        >
          This booking has been cancelled.
        </div>
        <div
          v-else-if="Number(booking.balance_due) <= 0"
          class="mt-6 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-6 text-center text-success"
        >
          This booking is fully paid. Thank you!
        </div>

        <div
          v-else-if="pendingOfflinePayment"
          class="mt-6 rounded-2xl border border-border-subtle bg-surface p-6 text-center shadow-sm"
        >
          <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-accent-bg/10 text-accent-strong">
            <svg class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
          </div>
          <h2 class="mt-4 font-[Georgia] text-lg font-bold text-foreground">Awaiting Confirmation</h2>
          <p v-if="pendingOfflinePayment.method === 'cash'" class="mt-2 text-sm text-foreground-muted">
            You've recorded a cash payment of KES {{ Number(pendingOfflinePayment.amount).toLocaleString() }} to
            {{ booking.driver_name }}. Once your driver confirms receiving it, your balance will be updated.
          </p>
          <p v-else class="mt-2 text-sm text-foreground-muted">
            You've declared a bank transfer of KES {{ Number(pendingOfflinePayment.amount).toLocaleString() }}
            <span v-if="pendingOfflinePayment.note">(ref. {{ pendingOfflinePayment.note }})</span>. Once our team
            confirms it's been received, your balance will be updated.
          </p>
        </div>

        <div
          v-else-if="requested"
          class="mt-6 rounded-2xl border border-border-subtle bg-surface p-6 text-center shadow-sm"
        >
          <template v-if="paymentOutcome === 'successful'">
            <div
              class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/10 text-success"
            >
              <svg class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 class="mt-4 font-[Georgia] text-lg font-bold text-foreground">Payment Received</h2>
            <p class="mt-2 text-sm text-foreground-muted">Thank you - your payment has been confirmed.</p>
          </template>

          <template v-else-if="paymentOutcome === 'failed'">
            <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-500/10 text-danger">
              <svg class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 class="mt-4 font-[Georgia] text-lg font-bold text-foreground">Payment Didn't Go Through</h2>
            <p class="mt-2 text-sm text-foreground-muted">
              The M-Pesa prompt was cancelled, timed out, or declined. No money has left your account.
            </p>
            <button
              class="mt-5 rounded-md bg-accent-bg px-5 py-2.5 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover"
              @click="retryPayment"
            >
              Try Again
            </button>
          </template>

          <template v-else-if="paymentOutcome === 'timeout'">
            <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-accent-bg/10 text-accent-strong">
              <svg class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
                />
              </svg>
            </div>
            <h2 class="mt-4 font-[Georgia] text-lg font-bold text-foreground">Still Waiting on M-Pesa</h2>
            <p class="mt-2 text-sm text-foreground-muted">
              This is taking longer than usual. If you already entered your PIN, refresh this page in a moment.
              Otherwise, you can try again.
            </p>
            <button
              class="mt-5 rounded-md bg-accent-bg px-5 py-2.5 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover"
              @click="retryPayment"
            >
              Try Again
            </button>
          </template>

          <template v-else>
            <div
              class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-accent-bg/10 text-accent-strong"
            >
              <svg class="h-7 w-7 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
              </svg>
            </div>
            <h2 class="mt-4 font-[Georgia] text-lg font-bold text-foreground">Check Your Phone</h2>
            <p class="mt-2 text-sm text-foreground-muted">
              We've sent an M-Pesa prompt to {{ phoneNumber }}. Enter your PIN to complete payment.
            </p>
          </template>
        </div>

        <div v-else class="mt-6 space-y-4 rounded-2xl border border-border-subtle bg-surface p-6">
          <div v-if="isWalkIn" class="text-sm text-foreground-muted">
            Paying in full: KES {{ Number(booking.balance_due).toLocaleString() }}.
          </div>
          <div v-else-if="!booking.is_deposit_paid">
            <label class="mb-1 block text-sm text-foreground-muted">How much would you like to pay now?</label>
            <div class="grid grid-cols-2 gap-3">
              <button
                type="button"
                class="rounded-md border px-3 py-2 text-sm font-semibold"
                :class="
                  payOption === 'deposit'
                    ? 'border-accent-border-strong bg-accent-bg text-on-accent'
                    : 'border-border text-foreground-secondary'
                "
                @click="payOption = 'deposit'"
              >
                Deposit (30%)<br />
                <span class="text-xs font-normal">KES {{ Number(booking.deposit_amount).toLocaleString() }}</span>
              </button>
              <button
                type="button"
                class="rounded-md border px-3 py-2 text-sm font-semibold"
                :class="
                  payOption === 'full'
                    ? 'border-accent-border-strong bg-accent-bg text-on-accent'
                    : 'border-border text-foreground-secondary'
                "
                @click="payOption = 'full'"
              >
                Pay in Full<br />
                <span class="text-xs font-normal">KES {{ Number(booking.balance_due).toLocaleString() }}</span>
              </button>
            </div>
          </div>
          <div v-else class="text-sm text-foreground-muted">
            Deposit already paid - paying the remaining balance of KES
            {{ Number(booking.balance_due).toLocaleString() }}.
          </div>

          <div v-if="booking.driver_name">
            <label class="mb-1 block text-sm text-foreground-muted">How would you like to pay?</label>
            <div class="grid gap-3" :class="booking.driver_cash_enabled ? 'grid-cols-2' : 'grid-cols-1'">
              <button
                type="button"
                class="rounded-md border px-3 py-2 text-sm font-semibold"
                :class="
                  paymentMethod === primaryMethod
                    ? 'border-accent-border-strong bg-accent-bg text-on-accent'
                    : 'border-border text-foreground-secondary'
                "
                @click="paymentMethod = primaryMethod"
              >
                {{ MPESA_ENABLED ? 'M-Pesa' : 'Bank Transfer' }}
              </button>
              <button
                v-if="booking.driver_cash_enabled"
                type="button"
                class="rounded-md border px-3 py-2 text-sm font-semibold"
                :class="
                  paymentMethod === 'cash'
                    ? 'border-accent-border-strong bg-accent-bg text-on-accent'
                    : 'border-border text-foreground-secondary'
                "
                @click="paymentMethod = 'cash'"
              >
                Cash
              </button>
            </div>
          </div>

          <template v-if="paymentMethod === 'cash' && booking.driver_name">
            <div class="rounded-md border border-border bg-surface-2 p-3 text-sm text-foreground-secondary">
              <label class="flex items-start gap-2">
                <input v-model="cashAcknowledged" type="checkbox" class="mt-0.5" />
                <span>
                  I confirm I am giving KES {{ amountToPay.toLocaleString() }} in cash directly to my driver,
                  {{ booking.driver_name }}.
                </span>
              </label>
            </div>

            <p v-if="cashError" class="text-sm text-danger">{{ cashError }}</p>

            <button
              :disabled="declaringCash || !cashAcknowledged"
              class="w-full rounded-md bg-accent-bg px-4 py-2.5 font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
              @click="declareCash"
            >
              {{ declaringCash ? 'Recording...' : `Record KES ${amountToPay.toLocaleString()} Cash Payment` }}
            </button>
          </template>

          <template v-else-if="paymentMethod === 'bank_transfer'">
            <div class="rounded-md border border-border bg-surface-2 p-4 text-sm text-foreground-secondary">
              <p class="font-semibold text-foreground">Pay via Bank Transfer</p>
              <p class="mt-2">Co-operative Bank of Kenya</p>
              <p>Paybill <span class="font-semibold text-foreground">400200</span></p>
              <p>Account No: <span class="font-semibold text-foreground">01101465587001</span></p>
              <p class="mt-2 text-xs text-foreground-subtle">
                Use your name and booking #{{ booking.id }} as the transfer reference, so we can match your payment.
              </p>
            </div>

            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Transaction reference</label>
              <input
                v-model="bankTransferReference"
                type="text"
                placeholder="e.g. last 4 digits of the M-Pesa/bank code"
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-foreground focus:border-accent-border focus:outline-none"
              />
              <p class="mt-1 text-xs text-foreground-subtle">
                Check the confirmation SMS from your bank/M-Pesa - at least the last 4 digits/characters are enough.
              </p>
            </div>

            <div class="rounded-md border border-border bg-surface-2 p-3 text-sm text-foreground-secondary">
              <label class="flex items-start gap-2">
                <input v-model="bankTransferAcknowledged" type="checkbox" class="mt-0.5" />
                <span>
                  I confirm I have sent KES {{ amountToPay.toLocaleString() }} via bank transfer to the account above.
                </span>
              </label>
            </div>

            <p v-if="bankTransferError" class="text-sm text-danger">{{ bankTransferError }}</p>

            <button
              :disabled="declaringBankTransfer || !bankTransferAcknowledged || bankTransferReference.trim().length < 4"
              class="w-full rounded-md bg-accent-bg px-4 py-2.5 font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
              @click="declareBankTransfer"
            >
              {{
                declaringBankTransfer
                  ? 'Recording...'
                  : `I've Sent KES ${amountToPay.toLocaleString()} via Bank Transfer`
              }}
            </button>
          </template>

          <template v-else>
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">M-Pesa Phone Number</label>
              <PhoneInput v-model="phoneNumber" required dark />
            </div>

            <p v-if="error" class="text-sm text-danger">{{ error }}</p>

            <button
              :disabled="submitting || !phoneNumber"
              class="w-full rounded-md bg-accent-bg px-4 py-2.5 font-semibold text-on-accent transition hover:bg-accent-bg-hover disabled:opacity-60"
              @click="payWithMpesa"
            >
              {{ submitting ? 'Sending prompt...' : `Pay KES ${amountToPay.toLocaleString()} via M-Pesa` }}
            </button>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>
