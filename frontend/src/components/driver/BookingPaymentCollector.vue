<script setup>
import { computed, ref } from 'vue'

import apiClient from '../../api/client'
import { useDriverPortalStore } from '../../stores/driverPortal'

// Collect payment for one booking: the client picks cash/card/bank-transfer (or M-Pesa, once
// MPESA_ENABLED below flips back on) + the exact amount they're paying; cash/card/bank transfer
// then need a separate confirmation that it was actually received (amount locked, not
// re-entered) - M-Pesa fires an STK Push immediately instead, no separate confirmation needed.
// Also handles logging a cash deposit to the Paybill once cash has been confirmed. Shared
// between the My Bookings list and the Walk-Up Client booking result screen - both just pass in
// a `booking` to act on.
const props = defineProps({
  booking: { type: Object, required: true },
})

// Temporary, easily-reversible: flip back to true once real M-Pesa production credentials are
// in place. Nothing about the M-Pesa flow itself (STK push against the client's own phone) is
// removed on the backend (see bookings.views.DriverDeclarePaymentView) - it's just not offered
// as a driver-facing option while this is false, in favor of bank transfer (which is itself
// still M-Pesa under the hood - Co-op Bank's own Paybill is paid via Lipa na M-Pesa - just
// routed to SilverLake's bank account instead of straight to its own Paybill).
const MPESA_ENABLED = false

const driverPortal = useDriverPortalStore()
// Superadmin-controlled (see Driver.cash_payments_enabled) - a driver with a history of cash
// disputes/undeposited cash can be forced onto non-cash methods only. Defaults to enabled (true)
// if the profile hasn't loaded yet, so the option doesn't flash away before it's known either way.
const cashEnabled = computed(() => driverPortal.profile?.cash_payments_enabled !== false)
const paymentMethodOptions = computed(() => {
  const options = cashEnabled.value ? ['cash', 'card'] : ['card']
  options.push(MPESA_ENABLED ? 'mpesa' : 'bank_transfer')
  return options
})

const paymentMethodDraft = ref('cash')
const paymentAmountDraft = ref('')
const bankTransferReferenceDraft = ref('')
const showForm = ref(false)
const declaring = ref(false)
const declareError = ref('')
const confirmingPaymentId = ref(null)
const confirmError = ref('')

function openPaymentForm() {
  showForm.value = true
  paymentMethodDraft.value = cashEnabled.value ? 'cash' : 'card'
  paymentAmountDraft.value = props.booking.balance_due
  bankTransferReferenceDraft.value = ''
  declareError.value = ''
}

async function declarePayment() {
  if (!paymentAmountDraft.value) return
  if (paymentMethodDraft.value === 'bank_transfer' && bankTransferReferenceDraft.value.trim().length < 4) return
  declareError.value = ''
  declaring.value = true
  try {
    const { data } = await apiClient.post(`/driver/bookings/${props.booking.id}/declare-payment/`, {
      method: paymentMethodDraft.value,
      amount: paymentAmountDraft.value,
      reference: bankTransferReferenceDraft.value,
    })
    Object.assign(props.booking, data)
    showForm.value = false
  } catch (err) {
    declareError.value = err.response?.data?.detail || 'Could not declare this payment.'
  } finally {
    declaring.value = false
  }
}

async function confirmPayment(payment) {
  confirmError.value = ''
  confirmingPaymentId.value = payment.id
  try {
    const { data } = await apiClient.post(`/driver/payments/${payment.id}/confirm/`)
    Object.assign(props.booking, data)
  } catch (err) {
    confirmError.value = err.response?.data?.detail || 'Could not confirm this payment.'
  } finally {
    confirmingPaymentId.value = null
  }
}

const depositFormPaymentId = ref(null)
const depositAmountDraft = ref('')
const depositReferenceDraft = ref('')
const loggingDepositId = ref(null)
const depositError = ref('')

function openDepositForm(payment) {
  depositFormPaymentId.value = payment.id
  depositAmountDraft.value = payment.amount
  depositReferenceDraft.value = ''
  depositError.value = ''
}

async function logCashDeposit(payment) {
  if (!depositAmountDraft.value || !depositReferenceDraft.value.trim()) return
  depositError.value = ''
  loggingDepositId.value = payment.id
  try {
    const { data } = await apiClient.post(`/driver/payments/${payment.id}/deposit/`, {
      amount: depositAmountDraft.value,
      mpesa_reference: depositReferenceDraft.value.trim(),
    })
    Object.assign(props.booking, data)
    depositFormPaymentId.value = null
  } catch (err) {
    depositError.value = err.response?.data?.detail || 'Could not log this deposit.'
  } finally {
    loggingDepositId.value = null
  }
}
</script>

<template>
  <div>
    <p
      v-if="
        booking.trip_ended_at && !['completed', 'cancelled'].includes(booking.status) && Number(booking.balance_due) > 0
      "
      class="mt-2 text-xs font-semibold text-amber-400"
    >
      Vehicle returned - awaiting final payment (KES {{ Number(booking.balance_due).toLocaleString() }}) to complete.
    </p>
    <p
      v-else-if="
        booking.trip_ended_at &&
        !['completed', 'cancelled'].includes(booking.status) &&
        booking.pending_cash_deposits?.length
      "
      class="mt-2 text-xs font-semibold text-amber-400"
    >
      Vehicle returned and fully paid - deposit the cash you collected below to complete this trip.
    </p>

    <!-- Collect payment: declare (client's chosen method + exact amount), then confirm once actually received -->
    <div
      v-if="booking.status !== 'cancelled' && (booking.pending_payments?.length || Number(booking.balance_due) > 0)"
      class="mt-3 border-t border-navy-800 pt-3"
    >
      <div v-if="booking.pending_payments?.length" class="space-y-2">
        <div
          v-for="payment in booking.pending_payments"
          :key="payment.id"
          class="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-gold-500/10 p-3"
        >
          <p class="text-xs font-semibold text-gold-400">
            KES {{ Number(payment.amount).toLocaleString() }} declared via
            {{
              payment.method === 'mpesa'
                ? 'M-Pesa'
                : payment.method === 'card'
                  ? 'card'
                  : payment.method === 'bank_transfer'
                    ? 'bank transfer'
                    : 'cash'
            }}<span v-if="payment.note"> (ref. {{ payment.note }})</span> -
            {{
              payment.method === 'bank_transfer'
                ? 'awaiting confirmation from our team.'
                : 'confirm once actually received.'
            }}
          </p>
          <!-- Bank transfer is staff-only to confirm - the driver never actually sees that
               money, only staff checking the real bank statement can vouch for it. -->
          <button
            v-if="payment.method !== 'bank_transfer'"
            :disabled="confirmingPaymentId === payment.id"
            class="shrink-0 rounded-md bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
            @click="confirmPayment(payment)"
          >
            {{ confirmingPaymentId === payment.id ? 'Confirming...' : 'Confirm Received' }}
          </button>
        </div>
        <p v-if="confirmError" class="text-xs text-red-400">{{ confirmError }}</p>
      </div>

      <div v-if="Number(booking.balance_due) > 0" class="mt-2">
        <button
          v-if="!showForm"
          class="text-xs font-semibold text-gold-400 hover:text-gold-300"
          @click="openPaymentForm"
        >
          + Collect Payment (KES {{ Number(booking.balance_due).toLocaleString() }} owed)
        </button>
        <template v-else>
          <div class="flex items-center justify-between">
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">Collect Payment</p>
            <button class="text-xs font-semibold text-slate-400 hover:text-white" @click="showForm = false">
              Cancel
            </button>
          </div>
          <form class="mt-2 space-y-2" @submit.prevent="declarePayment">
            <p v-if="declareError" class="text-xs text-red-400">{{ declareError }}</p>
            <div class="grid grid-cols-3 gap-2">
              <button
                v-for="opt in paymentMethodOptions"
                :key="opt"
                type="button"
                class="rounded-md border px-2 py-1.5 text-xs font-semibold capitalize"
                :class="
                  paymentMethodDraft === opt
                    ? 'border-gold-500 bg-gold-500 text-navy-950'
                    : 'border-navy-700 text-slate-300'
                "
                @click="paymentMethodDraft = opt"
              >
                {{ opt === 'mpesa' ? 'M-Pesa' : opt === 'bank_transfer' ? 'Bank Transfer' : opt }}
              </button>
            </div>
            <p v-if="!cashEnabled" class="text-[11px] text-slate-500">
              Cash payments are disabled for your account - use card or
              {{ MPESA_ENABLED ? 'M-Pesa' : 'bank transfer' }} instead.
            </p>
            <input
              v-model="paymentAmountDraft"
              type="number"
              min="0"
              step="0.01"
              :placeholder="`Amount (deposit: KES ${Number(booking.deposit_amount).toLocaleString()})`"
              required
              class="w-full rounded-md border border-navy-700 bg-navy-800 px-2 py-1.5 text-xs text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
            />
            <input
              v-if="paymentMethodDraft === 'bank_transfer'"
              v-model="bankTransferReferenceDraft"
              type="text"
              placeholder="Transaction reference (at least last 4 digits/characters)"
              required
              class="w-full rounded-md border border-navy-700 bg-navy-800 px-2 py-1.5 text-xs text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
            />
            <button
              type="submit"
              :disabled="
                declaring || (paymentMethodDraft === 'bank_transfer' && bankTransferReferenceDraft.trim().length < 4)
              "
              class="w-full rounded-md bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
            >
              {{ declaring ? 'Saving...' : paymentMethodDraft === 'mpesa' ? 'Send M-Pesa Prompt' : 'Declare Payment' }}
            </button>
          </form>
        </template>
      </div>
    </div>

    <!-- Cash deposits owed to the Paybill -->
    <div v-if="booking.pending_cash_deposits?.length" class="mt-3 space-y-2 border-t border-navy-800 pt-3">
      <div v-for="payment in booking.pending_cash_deposits" :key="payment.id" class="rounded-lg bg-gold-500/10 p-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <p class="text-xs font-semibold text-gold-400">
            KES {{ Number(payment.amount).toLocaleString() }} collected in cash - deposit this to Paybill 400400 (Acc:
            SILVERLAKE) and log it below.
          </p>
          <button
            v-if="depositFormPaymentId !== payment.id"
            class="shrink-0 text-xs font-semibold text-gold-400 hover:text-gold-300"
            @click="openDepositForm(payment)"
          >
            Log Deposit
          </button>
          <button
            v-else
            class="shrink-0 text-xs font-semibold text-slate-400 hover:text-white"
            @click="depositFormPaymentId = null"
          >
            Cancel
          </button>
        </div>
        <form
          v-if="depositFormPaymentId === payment.id"
          class="mt-2 space-y-2"
          @submit.prevent="logCashDeposit(payment)"
        >
          <p v-if="depositError" class="text-xs text-red-400">{{ depositError }}</p>
          <div class="flex flex-wrap gap-2">
            <input
              v-model="depositAmountDraft"
              type="number"
              min="0"
              step="0.01"
              placeholder="Amount deposited"
              required
              class="w-36 rounded-md border border-navy-700 bg-navy-800 px-2 py-1.5 text-xs text-white focus:border-gold-500 focus:outline-none"
            />
            <input
              v-model="depositReferenceDraft"
              type="text"
              placeholder="M-Pesa reference (e.g. QWE123RTY)"
              required
              class="flex-1 rounded-md border border-navy-700 bg-navy-800 px-2 py-1.5 text-xs text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            :disabled="loggingDepositId === payment.id"
            class="rounded-md bg-gold-500 px-3 py-1.5 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
          >
            {{ loggingDepositId === payment.id ? 'Saving...' : 'Confirm Deposit' }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
