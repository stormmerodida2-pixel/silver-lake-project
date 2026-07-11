<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useNotifications } from '../composables/useNotifications'

const props = defineProps({
  // '/admin/notifications' for the admin dashboard, '/driver/notifications' for the driver
  // portal - two separately scoped feeds on the backend (see notifications.views).
  basePath: { type: String, required: true },
})

const POLL_INTERVAL_MS = 30000

const router = useRouter()
const { unreadCount, items, loading, refreshCount, loadList, markRead, markAllRead } = useNotifications(props.basePath)

const root = ref(null)
const open = ref(false)
let pollTimer = null

const EVENT_LABELS = {
  // Admin dashboard
  driver_acknowledged: 'Driver Acknowledged',
  booking_created: 'New Booking',
  booking_cancelled: 'Booking Cancelled',
  cash_payment_recorded: 'Cash Payment',
  payment_disputed: 'Payment Disputed',
  dispute_resolved: 'Dispute Resolved',
  driver_away: 'Driver Away',
  vehicle_submission: 'Vehicle Submission',
  driver_application: 'Driver Application',
  // Driver portal
  driver_booked: 'New Booking',
  payment_reminder: 'Payment Reminder',
  cash_deposit_reminder: 'Deposit Reminder',
  payout_paid: 'Payout Paid',
  vehicle_submission_approved: 'Vehicle Approved',
  vehicle_submission_rejected: 'Vehicle Rejected',
}

function eventLabel(event) {
  return EVENT_LABELS[event] || event
}

function timeAgo(isoString) {
  const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

async function toggle() {
  open.value = !open.value
  if (open.value) await loadList()
}

async function selectNotification(notification) {
  await markRead(notification)
  open.value = false
  if (notification.link_path) router.push(notification.link_path)
}

function handleOutsideClick(event) {
  if (root.value && !root.value.contains(event.target)) open.value = false
}

onMounted(() => {
  refreshCount()
  pollTimer = setInterval(refreshCount, POLL_INTERVAL_MS)
  document.addEventListener('click', handleOutsideClick)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  document.removeEventListener('click', handleOutsideClick)
})
</script>

<template>
  <div ref="root" class="relative">
    <button
      class="relative flex h-9 w-9 items-center justify-center rounded-full text-slate-300 transition hover:bg-navy-800 hover:text-gold-400"
      aria-label="Notifications"
      @click="toggle"
    >
      <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 1 0-12 0v3.2a2 2 0 0 1-.6 1.4L4 17h5m6 0v1a3 3 0 1 1-6 0v-1m6 0H9" />
      </svg>
      <span
        v-if="unreadCount > 0"
        class="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white"
      >
        {{ unreadCount > 9 ? '9+' : unreadCount }}
      </span>
    </button>

    <div
      v-if="open"
      class="absolute right-0 z-50 mt-2 w-80 rounded-xl border border-navy-700 bg-navy-900 shadow-2xl shadow-black/40"
    >
      <div class="flex items-center justify-between border-b border-navy-800 px-4 py-3">
        <span class="font-[Georgia] text-sm font-bold text-white">Notifications</span>
        <button
          v-if="unreadCount > 0"
          class="text-xs font-semibold text-gold-400 hover:text-gold-300"
          @click="markAllRead"
        >
          Mark all read
        </button>
      </div>

      <div class="max-h-96 overflow-y-auto">
        <p v-if="loading" class="p-4 text-center text-xs text-slate-500">Loading...</p>
        <p v-else-if="!items.length" class="p-4 text-center text-xs text-slate-500">No notifications yet.</p>
        <button
          v-for="notification in items"
          :key="notification.id"
          class="flex w-full items-start gap-2.5 border-b border-navy-800 px-4 py-3 text-left transition hover:bg-navy-800"
          @click="selectNotification(notification)"
        >
          <span
            class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
            :class="notification.is_read ? 'bg-transparent' : 'bg-gold-400'"
          />
          <span class="min-w-0 flex-1">
            <span class="block text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              {{ eventLabel(notification.event) }}
            </span>
            <span class="mt-0.5 block text-sm" :class="notification.is_read ? 'text-slate-400' : 'text-white'">
              {{ notification.message }}
            </span>
            <span class="mt-0.5 block text-xs text-slate-500">{{ timeAgo(notification.created_at) }}</span>
          </span>
        </button>
      </div>
    </div>
  </div>
</template>
