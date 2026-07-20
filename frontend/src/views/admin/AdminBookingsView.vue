<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import apiClient from '../../api/client'
import ConditionReportModal from '../../components/ConditionReportModal.vue'
import GovernmentBookingModal from '../../components/admin/GovernmentBookingModal.vue'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'
import { confirmDialog } from '../../utils/dialogs'

const auth = useAuthStore()
const route = useRoute()
// Pre-fills from a ?search= query param so a link from an escalation email/notification
// (see bookings.emails.send_acknowledgment_overdue_staff_notification_email) can land staff
// directly on the specific booking that needs attention, not just the unfiltered list.
const filters = reactive({ search: route.query.search || '', status: '', service_type: '' })
const { items: bookings, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/bookings/', filters)
const { items: driverOptions, load: loadDriverOptions } = useAdminList('/admin/drivers/')
const busyId = ref(null)

const statusOptions = ['pending', 'confirmed', 'ongoing', 'completed', 'cancelled']

async function changeStatus(booking, newStatus) {
  if (newStatus === booking.status) return

  // Cancelling a booking the driver already acknowledged normally only refunds half of what's
  // been paid - unless the driver was actually the reason it's being cancelled (went
  // unavailable, or delayed without telling anyone), in which case it should be a full refund.
  let driverAtFault = false
  if (newStatus === 'cancelled' && booking.driver_acknowledged_at) {
    driverAtFault = await confirmDialog(
      "The driver already acknowledged this trip, so cancelling it normally only refunds half of what's been paid. " +
      "Was this the driver's fault (went unavailable, or delayed without telling anyone)?",
      { confirmText: "Yes, driver's fault - full refund", cancelText: 'No - standard 50% refund' },
    )
  }

  busyId.value = booking.id
  try {
    const { data } = await apiClient.post(`/admin/bookings/${booking.id}/set-status/`, {
      status: newStatus,
      ...(newStatus === 'cancelled' ? { driver_at_fault: driverAtFault } : {}),
    })
    Object.assign(booking, data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not update booking status.'
  } finally {
    busyId.value = null
  }
}

async function changeDriver(booking, driverId) {
  busyId.value = booking.id
  try {
    const { data } = await apiClient.patch(`/admin/bookings/${booking.id}/`, { driver: driverId || null })
    Object.assign(booking, data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not reassign driver.'
  } finally {
    busyId.value = null
  }
}

function isUnderpaid(booking) {
  return Number(booking.balance_due) > 0 && booking.status !== 'cancelled'
}

function isAwaitingAcknowledgment(booking) {
  return (
    booking.service_type === 'with_driver' && !!booking.driver_name && !booking.driver_acknowledged_at
    && ['pending', 'confirmed'].includes(booking.status)
  )
}

function canRemindBalance(booking) {
  return isUnderpaid(booking) && !!booking.driver_name
}

function balanceRemindDisabledReason(booking) {
  if (!booking.last_balance_reminder_at) return null
  const elapsedMs = Date.now() - new Date(booking.last_balance_reminder_at).getTime()
  return elapsedMs < 60 * 60 * 1000 ? 'Reminded recently - please wait before sending another.' : null
}

async function remindBalance(booking) {
  busyId.value = booking.id
  try {
    const { data } = await apiClient.post(`/admin/bookings/${booking.id}/remind_balance/`)
    Object.assign(booking, data)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not send a reminder for this booking.'
  } finally {
    busyId.value = null
  }
}

// ── Government contract bookings ─────────────────────────────────────────────
const showGovModal = ref(false)
const govModal = ref(null)

function openGovModal() {
  govModal.value.open()
  showGovModal.value = true
}

function onGovernmentBookingCreated(booking) {
  bookings.value.unshift(booking)
}

const recordingInvoiceId = ref(null)
const invoiceForm = reactive({ amount: '', reference: '' })
const invoiceError = ref('')

function openInvoiceForm(booking) {
  recordingInvoiceId.value = booking.id
  invoiceError.value = ''
  Object.assign(invoiceForm, { amount: '', reference: '' })
}

async function submitInvoicePayment(booking) {
  invoiceError.value = ''
  busyId.value = booking.id
  try {
    const { data } = await apiClient.post(`/admin/bookings/${booking.id}/record-invoice-payment/`, {
      amount: invoiceForm.amount,
      reference: invoiceForm.reference,
    })
    Object.assign(booking, data)
    recordingInvoiceId.value = null
  } catch (err) {
    invoiceError.value = err.response?.data?.detail || 'Could not record this payment.'
  } finally {
    busyId.value = null
  }
}

// ── Condition report (optional - never blocks a status change) ──────────────────────────────
const showConditionModal = ref(false)
const conditionModal = ref(null)
const conditionBookingId = ref(null)
const conditionReportType = ref('pickup')
const conditionEndpoint = computed(() => `/admin/bookings/${conditionBookingId.value}/condition-reports/`)

function openConditionModal(booking, reportType) {
  conditionBookingId.value = booking.id
  conditionReportType.value = reportType
  conditionModal.value.open()
  showConditionModal.value = true
}

const downloadingId = ref(null)
async function downloadReceipt(booking) {
  downloadingId.value = booking.id
  try {
    // Same customer-facing endpoint, not /admin/bookings/ - BookingViewSet.get_queryset()
    // already scopes staff to their own org (or everyone, platform-wide), so no separate
    // admin route is needed for this.
    const response = await apiClient.get(`/bookings/${booking.id}/receipt/`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `SilverLake-Receipt-${booking.id}.pdf`
    link.click()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    error.value = 'Could not download the receipt.'
  } finally {
    downloadingId.value = null
  }
}

onMounted(() => {
  load()
  loadDriverOptions()
})
</script>

<template>
  <div>
    <h1 class="font-[Georgia] text-2xl font-bold text-white">Manage Bookings</h1>

    <div class="mt-4 flex flex-wrap gap-3">
      <input
        v-model="filters.search"
        type="text"
        placeholder="Search by customer name, phone or email..."
        class="min-w-64 flex-1 rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-gold-400 focus:outline-none"
      />
      <select
        v-model="filters.status"
        class="rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-sm text-white focus:border-gold-400 focus:outline-none"
      >
        <option value="">All statuses</option>
        <option v-for="option in statusOptions" :key="option" :value="option">
          {{ option.charAt(0).toUpperCase() + option.slice(1) }}
        </option>
      </select>
      <select
        v-model="filters.service_type"
        class="rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-sm text-white focus:border-gold-400 focus:outline-none"
      >
        <option value="">All service types</option>
        <option value="with_driver">With Driver</option>
        <option value="self_drive">Self Drive</option>
      </select>
      <button
        class="rounded-md bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition hover:bg-gold-400"
        @click="openGovModal"
      >
        + Contract Booking
      </button>
    </div>

    <GovernmentBookingModal
      ref="govModal"
      v-model="showGovModal"
      :driver-options="driverOptions"
      @created="onGovernmentBookingCreated"
    />
    <ConditionReportModal
      ref="conditionModal" v-model="showConditionModal"
      :endpoint="conditionEndpoint" :report-type="conditionReportType"
    />

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <div v-if="!loading" class="mt-6 overflow-x-auto rounded-xl border border-navy-800">
      <table class="w-full text-left text-sm">
        <thead class="bg-navy-900 text-slate-400">
          <tr>
            <th class="px-4 py-3">Customer</th>
            <th class="px-4 py-3">Vehicle</th>
            <th class="px-4 py-3">Service</th>
            <th class="px-4 py-3">Dates</th>
            <th class="px-4 py-3">Total</th>
            <th class="px-4 py-3">Paid</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Trip</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-navy-800 bg-navy-950">
          <tr
            v-for="booking in bookings"
            :key="booking.id"
            :class="booking.needs_attention ? 'bg-red-500/5' : ''"
          >
            <td class="px-4 py-3 text-white">
              {{ booking.customer_name }}
              <div class="text-xs text-slate-500">{{ booking.customer_phone }}</div>
              <span
                v-if="booking.source === 'driver_onsite'"
                class="mt-1 inline-block rounded-full bg-navy-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gold-400"
              >
                Walk-in
              </span>
              <span
                v-if="booking.is_government_contract"
                :title="booking.government_contract_reference"
                class="mt-1 inline-block rounded-full bg-brand-blue-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand-blue-400"
              >
                Contract: {{ booking.government_contract_reference }}
              </span>
            </td>
            <td class="px-4 py-3 text-slate-300">
              {{ booking.vehicle_name }}
            </td>
            <td class="px-4 py-3 text-slate-300">
              {{ booking.service_type === 'with_driver' ? 'With Driver' : 'Self Drive' }}
              <select
                v-if="booking.service_type === 'with_driver' && auth.user?.is_superuser"
                :value="booking.driver || ''"
                :disabled="busyId === booking.id"
                class="mt-1 block rounded-md border border-navy-700 bg-navy-950 px-2 py-1 text-xs text-white focus:border-gold-400 focus:outline-none disabled:opacity-50"
                @change="changeDriver(booking, $event.target.value ? Number($event.target.value) : null)"
              >
                <option value="">No driver assigned</option>
                <option v-for="d in driverOptions" :key="d.id" :value="d.id">{{ d.full_name }}</option>
              </select>
              <div v-else-if="booking.driver_name" class="text-xs text-slate-500">{{ booking.driver_name }}</div>
            </td>
            <td class="px-4 py-3 text-slate-400">{{ booking.start_date }} to {{ booking.end_date }}</td>
            <td class="px-4 py-3 text-slate-300">KES {{ Number(booking.total_amount).toLocaleString() }}</td>
            <td class="px-4 py-3 text-slate-300">
              KES {{ Number(booking.amount_paid).toLocaleString() }}
              <div v-if="isUnderpaid(booking)" class="mt-1">
                <div class="text-xs font-semibold text-red-400">
                  Balance due: KES {{ Number(booking.balance_due).toLocaleString() }}
                </div>
                <button
                  v-if="canRemindBalance(booking)"
                  :disabled="busyId === booking.id || !!balanceRemindDisabledReason(booking)"
                  :title="balanceRemindDisabledReason(booking) || ''"
                  class="mt-1 rounded-md border border-navy-700 px-2 py-0.5 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                  @click="remindBalance(booking)"
                >
                  {{ busyId === booking.id ? 'Sending...' : (booking.last_balance_reminder_at ? 'Remind Again' : 'Remind Driver') }}
                </button>
                <p v-else-if="!booking.driver_name" class="text-xs text-slate-600">No driver to remind</p>

                <div v-if="booking.is_government_contract" class="mt-2">
                  <button
                    v-if="recordingInvoiceId !== booking.id"
                    class="rounded-md border border-brand-blue-500 px-2 py-0.5 text-xs font-semibold text-brand-blue-400 hover:bg-brand-blue-500 hover:text-white"
                    @click="openInvoiceForm(booking)"
                  >
                    Record Invoice Payment
                  </button>
                  <div v-else class="space-y-1.5 rounded-md border border-navy-700 bg-navy-900 p-2">
                    <input
                      v-model="invoiceForm.amount" type="number" step="0.01" placeholder="Amount (KES)"
                      class="w-full rounded border border-navy-700 bg-navy-950 px-2 py-1 text-xs text-white focus:border-gold-400 focus:outline-none"
                    />
                    <input
                      v-model="invoiceForm.reference" type="text" placeholder="Reference (optional)"
                      class="w-full rounded border border-navy-700 bg-navy-950 px-2 py-1 text-xs text-white focus:border-gold-400 focus:outline-none"
                    />
                    <p v-if="invoiceError" class="text-xs text-red-400">{{ invoiceError }}</p>
                    <div class="flex gap-1.5">
                      <button
                        class="flex-1 rounded border border-navy-700 px-2 py-1 text-xs text-slate-300 hover:border-slate-500"
                        @click="recordingInvoiceId = null"
                      >
                        Cancel
                      </button>
                      <button
                        :disabled="busyId === booking.id"
                        class="flex-1 rounded bg-gold-500 px-2 py-1 text-xs font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-50"
                        @click="submitInvoicePayment(booking)"
                      >
                        {{ busyId === booking.id ? 'Saving...' : 'Save' }}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <button
                v-if="Number(booking.amount_paid) > 0"
                :disabled="downloadingId === booking.id"
                class="mt-1 rounded-md border border-navy-700 px-2 py-0.5 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="downloadReceipt(booking)"
              >
                {{ downloadingId === booking.id ? 'Downloading...' : 'Receipt' }}
              </button>
            </td>
            <td class="px-4 py-3">
              <select
                :value="booking.status"
                :disabled="busyId === booking.id"
                class="rounded-md border border-navy-700 bg-navy-950 px-2 py-1 text-xs text-white focus:border-gold-400 focus:outline-none disabled:opacity-50"
                @change="changeStatus(booking, $event.target.value)"
              >
                <option v-for="option in statusOptions" :key="option" :value="option">
                  {{ option.charAt(0).toUpperCase() + option.slice(1) }}
                </option>
              </select>
            </td>
            <td class="px-4 py-3 text-xs">
              <span
                v-if="booking.needs_attention"
                class="mb-1 inline-block rounded-full bg-red-500/10 px-2 py-0.5 font-semibold text-red-400"
              >
                Needs Attention
              </span>
              <div v-if="booking.service_type === 'with_driver' && booking.driver_name">
                <div v-if="booking.driver_acknowledged_at" class="text-slate-500">
                  Acknowledged {{ new Date(booking.driver_acknowledged_at).toLocaleString() }}
                </div>
                <span
                  v-else-if="isAwaitingAcknowledgment(booking)"
                  class="inline-block rounded-full bg-gold-500/10 px-2 py-0.5 font-semibold text-gold-400"
                  title="The driver hasn't opened/acknowledged this booking on their dashboard yet"
                >
                  Awaiting Acknowledgment
                </span>
              </div>
              <div v-if="booking.trip_started_at" class="text-slate-500">Started {{ new Date(booking.trip_started_at).toLocaleDateString() }}</div>
              <div v-if="booking.trip_ended_at" class="text-slate-500">Ended {{ new Date(booking.trip_ended_at).toLocaleDateString() }}</div>
              <div
                v-if="!booking.trip_started_at && !booking.trip_ended_at && !booking.needs_attention && !booking.driver_acknowledged_at && !isAwaitingAcknowledgment(booking)"
                class="text-slate-600"
              >
                —
              </div>
              <div v-if="['confirmed', 'ongoing', 'completed'].includes(booking.status)" class="mt-1.5 flex gap-1">
                <button
                  class="rounded border border-navy-800 px-1.5 py-0.5 text-slate-500 hover:border-gold-400 hover:text-gold-400"
                  @click="openConditionModal(booking, 'pickup')"
                >
                  + Pickup
                </button>
                <button
                  class="rounded border border-navy-800 px-1.5 py-0.5 text-slate-500 hover:border-gold-400 hover:text-gold-400"
                  @click="openConditionModal(booking, 'return')"
                >
                  + Return
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!bookings.length" class="p-6 text-center text-slate-400">No bookings yet.</p>
      <div v-if="nextUrl" class="border-t border-navy-800 p-3 text-center">
        <button
          :disabled="loadingMore"
          class="rounded-md border border-navy-700 px-4 py-1.5 text-sm font-medium text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
          @click="loadMore"
        >
          {{ loadingMore ? 'Loading...' : 'Load More' }}
        </button>
      </div>
    </div>
  </div>
</template>
