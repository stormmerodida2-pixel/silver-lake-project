<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'

const { items: tickets, loading, error, load } = useAdminList('/admin/support/')
const busyId = ref(null)

const categoryLabels = {
  billing: 'Billing Question',
  damage_dispute: 'Damage / Condition Dispute',
  booking_issue: 'Booking Issue',
  other: 'Other',
}
const statusLabels = { open: 'Open', in_progress: 'In Progress', resolved: 'Resolved' }
const statusClasses = {
  open: 'bg-accent-bg/10 text-accent',
  in_progress: 'bg-brand-blue-500/10 text-brand-blue-400',
  resolved: 'bg-emerald-500/10 text-success',
}

async function markInProgress(ticket) {
  busyId.value = ticket.id
  try {
    const { data } = await apiClient.post(`/admin/support/${ticket.id}/respond/`, { status: 'in_progress' })
    Object.assign(ticket, data)
  } catch {
    error.value = 'Could not update this ticket.'
  } finally {
    busyId.value = null
  }
}

// ── Resolve form ──────────────────────────────────────────────────────────────
const resolvingId = ref(null)
const resolutionNote = ref('')
const resolveError = ref('')

function openResolveForm(ticket) {
  resolvingId.value = ticket.id
  resolutionNote.value = ''
  resolveError.value = ''
}

async function submitResolution(ticket) {
  resolveError.value = ''
  busyId.value = ticket.id
  try {
    const { data } = await apiClient.post(`/admin/support/${ticket.id}/respond/`, {
      status: 'resolved',
      resolution_note: resolutionNote.value,
    })
    Object.assign(ticket, data)
    resolvingId.value = null
  } catch (err) {
    resolveError.value = err.response?.data?.detail || 'Could not resolve this ticket.'
  } finally {
    busyId.value = null
  }
}

onMounted(() => {
  load()
})
</script>

<template>
  <div>
    <h1 class="font-[Georgia] text-2xl font-bold text-foreground">Support Tickets</h1>
    <p class="mt-1 text-sm text-foreground-muted">
      Billing questions, damage disputes, and other issues customers raise from their own account.
    </p>

    <p v-if="loading" class="mt-10 text-center text-foreground-muted">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-danger">{{ error }}</p>

    <div v-if="!loading" class="mt-6 space-y-3">
      <div v-for="ticket in tickets" :key="ticket.id" class="rounded-xl border border-border-subtle bg-surface p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <p class="font-semibold text-foreground">{{ ticket.subject }}</p>
              <span
                class="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent"
              >
                {{ categoryLabels[ticket.category] }}
              </span>
              <span
                class="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                :class="statusClasses[ticket.status]"
              >
                {{ statusLabels[ticket.status] }}
              </span>
            </div>
            <p class="mt-1 text-xs text-foreground-subtle">
              {{ ticket.customer_name }} ({{ ticket.customer_email }})
              <template v-if="ticket.booking_label"> &middot; {{ ticket.booking_label }}</template>
              &middot; {{ new Date(ticket.created_at).toLocaleString() }}
            </p>
            <p class="mt-2 whitespace-pre-line text-sm text-foreground-secondary">{{ ticket.description }}</p>
            <div v-if="ticket.photos.length" class="mt-2 flex flex-wrap gap-2">
              <a v-for="photo in ticket.photos" :key="photo.id" :href="photo.image" target="_blank" rel="noopener">
                <img
                  :src="photo.image"
                  alt="Attached photo"
                  class="h-16 w-16 rounded-lg border border-border object-cover"
                />
              </a>
            </div>
            <p
              v-if="ticket.status === 'resolved'"
              class="mt-2 rounded-lg bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300"
            >
              <span class="font-semibold">Resolved by {{ ticket.resolved_by_name }}:</span> {{ ticket.resolution_note }}
            </p>
          </div>
          <div v-if="ticket.status !== 'resolved'" class="flex shrink-0 flex-col items-end gap-2">
            <button
              v-if="ticket.status === 'open'"
              :disabled="busyId === ticket.id"
              class="rounded-md border border-border px-2 py-1 text-xs font-semibold text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
              @click="markInProgress(ticket)"
            >
              Mark In Progress
            </button>
            <button
              v-if="resolvingId !== ticket.id"
              class="rounded-md border border-emerald-500 px-2 py-1 text-xs font-semibold text-success hover:bg-emerald-500 hover:text-on-accent"
              @click="openResolveForm(ticket)"
            >
              Resolve
            </button>
          </div>
        </div>

        <div v-if="resolvingId === ticket.id" class="mt-3 space-y-2 rounded-lg border border-border bg-page p-3">
          <textarea
            v-model="resolutionNote"
            rows="2"
            placeholder="Describe how this was resolved..."
            class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-foreground placeholder-foreground-subtle focus:border-accent-border focus:outline-none"
          ></textarea>
          <p v-if="resolveError" class="text-xs text-danger">{{ resolveError }}</p>
          <div class="flex justify-end gap-2">
            <button
              class="rounded-md border border-border px-3 py-1.5 text-xs font-semibold text-foreground-secondary hover:border-slate-500"
              @click="resolvingId = null"
            >
              Cancel
            </button>
            <button
              :disabled="busyId === ticket.id"
              class="rounded-md bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-on-accent hover:bg-emerald-400 disabled:opacity-50"
              @click="submitResolution(ticket)"
            >
              {{ busyId === ticket.id ? 'Saving...' : 'Mark Resolved' }}
            </button>
          </div>
        </div>
      </div>
      <p v-if="!tickets.length" class="p-6 text-center text-foreground-muted">No support tickets yet.</p>
    </div>
  </div>
</template>
