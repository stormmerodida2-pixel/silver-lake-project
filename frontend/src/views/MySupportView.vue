<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import apiClient from '../api/client'

const route = useRoute()

const tickets = ref([])
const loading = ref(true)
const error = ref('')
const bookings = ref([])

const categoryLabels = {
  billing: 'Billing Question',
  damage_dispute: 'Damage / Condition Dispute',
  booking_issue: 'Booking Issue',
  other: 'Other',
}
const statusLabels = {
  open: 'Open',
  in_progress: 'In Progress',
  resolved: 'Resolved',
}
const statusStyles = {
  open: 'bg-accent-bg/10 text-accent border border-accent-border-strong/20',
  in_progress: 'bg-blue-500/10 text-info border border-blue-500/20',
  resolved: 'bg-emerald-500/10 text-success border border-emerald-500/20',
}

async function loadTickets() {
  loading.value = true
  try {
    const { data } = await apiClient.get('/support/tickets/')
    tickets.value = data.results ?? data
  } catch {
    error.value = 'Could not load your support tickets.'
  } finally {
    loading.value = false
  }
}

async function loadBookings() {
  try {
    const { data } = await apiClient.get('/bookings/')
    bookings.value = data.results ?? data
  } catch {
    // Advisory only - the booking picker just stays empty if this fails.
  }
}

// ── New ticket form ───────────────────────────────────────────────────────────
const showForm = ref(false)
const saving = ref(false)
const formError = ref('')
const form = reactive({
  category: 'other',
  subject: '',
  description: '',
  booking: route.query.booking ? Number(route.query.booking) : '',
})
const photoFiles = ref([])

function openForm() {
  showForm.value = true
  formError.value = ''
}

function onPhotosSelected(event) {
  photoFiles.value = [...photoFiles.value, ...Array.from(event.target.files)]
  event.target.value = ''
}
function removePhoto(index) {
  photoFiles.value = photoFiles.value.filter((_, i) => i !== index)
}

function bookingLabel(booking) {
  return `${booking.vehicle_name} (${booking.start_date} to ${booking.end_date})`
}

async function submitTicket() {
  formError.value = ''
  if (!form.subject.trim() || !form.description.trim()) {
    formError.value = 'Please fill in a subject and description.'
    return
  }
  saving.value = true
  try {
    const payload = new FormData()
    payload.append('category', form.category)
    payload.append('subject', form.subject)
    payload.append('description', form.description)
    if (form.booking) payload.append('booking', form.booking)
    photoFiles.value.forEach((file) => payload.append('photos', file))

    const { data } = await apiClient.post('/support/tickets/', payload)
    tickets.value.unshift(data)
    showForm.value = false
    Object.assign(form, { category: 'other', subject: '', description: '', booking: '' })
    photoFiles.value = []
  } catch (err) {
    const detail = err?.response?.data
    formError.value =
      typeof detail === 'object'
        ? Object.values(detail).flat().join(' ')
        : 'Could not submit your ticket. Please try again.'
  } finally {
    saving.value = false
  }
}

// ── Reopen ──────────────────────────────────────────────────────────────────
const reopeningId = ref(null)
async function reopenTicket(ticket) {
  reopeningId.value = ticket.id
  try {
    const { data } = await apiClient.post(`/support/tickets/${ticket.id}/reopen/`)
    const index = tickets.value.findIndex((t) => t.id === ticket.id)
    tickets.value[index] = data
  } catch {
    error.value = 'Could not reopen this ticket.'
  } finally {
    reopeningId.value = null
  }
}

onMounted(() => {
  loadTickets()
  loadBookings()
  if (route.query.booking) openForm()
})
</script>

<template>
  <div class="bg-page">
    <div class="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <div class="flex items-center justify-between">
        <h1 class="font-[Georgia] text-3xl font-bold text-foreground">Support</h1>
        <button
          class="rounded-md bg-accent-bg px-4 py-2 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover"
          @click="openForm"
        >
          + New Ticket
        </button>
      </div>
      <p class="mt-2 text-foreground-muted">
        Raise a billing question, dispute a charge, or report an issue with a trip - and track it here.
      </p>

      <!-- New ticket form -->
      <div v-if="showForm" class="mt-6 rounded-xl border border-border-subtle bg-surface p-6">
        <p
          v-if="formError"
          class="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-danger"
        >
          {{ formError }}
        </p>
        <form class="space-y-4" @submit.prevent="submitTicket">
          <div class="grid gap-4 sm:grid-cols-2">
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Category</label>
              <select
                v-model="form.category"
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              >
                <option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm text-foreground-muted">Related booking (optional)</label>
              <select
                v-model="form.booking"
                class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground focus:border-accent-border focus:outline-none"
              >
                <option value="">None</option>
                <option v-for="booking in bookings" :key="booking.id" :value="booking.id">
                  {{ bookingLabel(booking) }}
                </option>
              </select>
            </div>
          </div>
          <div>
            <label class="mb-1 block text-sm text-foreground-muted">Subject</label>
            <input
              v-model="form.subject"
              type="text"
              required
              placeholder="Short summary of the issue"
              class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground placeholder-foreground-subtle focus:border-accent-border focus:outline-none"
            />
          </div>
          <div>
            <label class="mb-1 block text-sm text-foreground-muted">Description</label>
            <textarea
              v-model="form.description"
              rows="4"
              required
              placeholder="Tell us what happened"
              class="w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground placeholder-foreground-subtle focus:border-accent-border focus:outline-none"
            ></textarea>
          </div>
          <div>
            <label class="mb-1 block text-sm text-foreground-muted">Photos (optional)</label>
            <input
              type="file"
              accept="image/*"
              multiple
              class="w-full text-sm text-foreground-muted file:mr-3 file:rounded-md file:border-0 file:bg-surface-2 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-foreground"
              @change="onPhotosSelected"
            />
            <div v-if="photoFiles.length" class="mt-2 flex flex-wrap gap-2">
              <div
                v-for="(file, i) in photoFiles"
                :key="i"
                class="flex items-center gap-1.5 rounded-full bg-surface-2 px-3 py-1 text-xs text-foreground-secondary shadow-sm"
              >
                {{ file.name }}
                <button type="button" class="font-bold text-danger" @click="removePhoto(i)">&times;</button>
              </div>
            </div>
          </div>
          <div class="flex justify-end gap-3">
            <button
              type="button"
              class="rounded-md border border-border px-4 py-2 text-sm font-semibold text-foreground hover:bg-surface-2"
              @click="showForm = false"
            >
              Cancel
            </button>
            <button
              type="submit"
              :disabled="saving"
              class="rounded-md bg-accent-bg px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-bg-hover disabled:opacity-60"
            >
              {{ saving ? 'Submitting…' : 'Submit Ticket' }}
            </button>
          </div>
        </form>
      </div>

      <p v-if="loading" class="mt-10 text-center text-foreground-subtle">Loading...</p>
      <p v-else-if="error" class="mt-10 text-center text-danger">{{ error }}</p>
      <p v-else-if="!tickets.length" class="mt-10 text-center text-foreground-subtle">You haven't filed any support tickets.</p>

      <div v-else class="mt-8 space-y-4">
        <div v-for="ticket in tickets" :key="ticket.id" class="rounded-xl border border-border-subtle bg-surface p-5">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 class="font-[Georgia] text-lg font-bold text-foreground">{{ ticket.subject }}</h3>
              <p class="text-sm text-foreground-subtle">
                {{ categoryLabels[ticket.category] }}
                <template v-if="ticket.booking_label"> &middot; {{ ticket.booking_label }}</template>
                &middot; {{ new Date(ticket.created_at).toLocaleDateString() }}
              </p>
            </div>
            <span
              class="rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase"
              :class="statusStyles[ticket.status]"
            >
              {{ statusLabels[ticket.status] }}
            </span>
          </div>
          <p class="mt-3 whitespace-pre-line text-sm text-foreground-secondary">{{ ticket.description }}</p>
          <div v-if="ticket.photos.length" class="mt-3 flex flex-wrap gap-2">
            <a v-for="photo in ticket.photos" :key="photo.id" :href="photo.image" target="_blank" rel="noopener">
              <img
                :src="photo.image"
                alt="Attached photo"
                class="h-16 w-16 rounded-lg border border-border-subtle object-cover"
              />
            </a>
          </div>

          <div
            v-if="ticket.status === 'resolved'"
            class="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-4"
          >
            <p class="text-xs font-semibold uppercase tracking-wide text-success">Resolution</p>
            <p class="mt-1 whitespace-pre-line text-sm text-emerald-200">{{ ticket.resolution_note }}</p>
            <button
              :disabled="reopeningId === ticket.id"
              class="mt-3 rounded-md border border-emerald-500/40 px-3 py-1.5 text-xs font-semibold text-success transition hover:bg-emerald-500 hover:text-foreground disabled:opacity-60"
              @click="reopenTicket(ticket)"
            >
              {{ reopeningId === ticket.id ? 'Reopening…' : 'Not resolved? Reopen' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
