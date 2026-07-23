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
  open: 'bg-gold-500/10 text-gold-700',
  in_progress: 'bg-brand-blue-50 text-brand-blue-600',
  resolved: 'bg-emerald-50 text-emerald-600',
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
  <div class="bg-white">
    <div class="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <div class="flex items-center justify-between">
        <h1 class="font-[Georgia] text-3xl font-bold text-navy-900">Support</h1>
        <button
          class="rounded-md bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition hover:bg-gold-400"
          @click="openForm"
        >
          + New Ticket
        </button>
      </div>
      <p class="mt-2 text-slate-500">
        Raise a billing question, dispute a charge, or report an issue with a trip - and track it here.
      </p>

      <!-- New ticket form -->
      <div v-if="showForm" class="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-6">
        <p v-if="formError" class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ formError }}
        </p>
        <form class="space-y-4" @submit.prevent="submitTicket">
          <div class="grid gap-4 sm:grid-cols-2">
            <div>
              <label class="mb-1 block text-sm text-slate-600">Category</label>
              <select
                v-model="form.category"
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              >
                <option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm text-slate-600">Related booking (optional)</label>
              <select
                v-model="form.booking"
                class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 focus:border-brand-blue-500 focus:outline-none"
              >
                <option value="">None</option>
                <option v-for="booking in bookings" :key="booking.id" :value="booking.id">
                  {{ bookingLabel(booking) }}
                </option>
              </select>
            </div>
          </div>
          <div>
            <label class="mb-1 block text-sm text-slate-600">Subject</label>
            <input
              v-model="form.subject"
              type="text"
              required
              placeholder="Short summary of the issue"
              class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 placeholder-slate-400 focus:border-brand-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label class="mb-1 block text-sm text-slate-600">Description</label>
            <textarea
              v-model="form.description"
              rows="4"
              required
              placeholder="Tell us what happened"
              class="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-navy-900 placeholder-slate-400 focus:border-brand-blue-500 focus:outline-none"
            ></textarea>
          </div>
          <div>
            <label class="mb-1 block text-sm text-slate-600">Photos (optional)</label>
            <input
              type="file"
              accept="image/*"
              multiple
              class="w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-navy-900 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-white"
              @change="onPhotosSelected"
            />
            <div v-if="photoFiles.length" class="mt-2 flex flex-wrap gap-2">
              <div
                v-for="(file, i) in photoFiles"
                :key="i"
                class="flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs text-slate-600 shadow-sm"
              >
                {{ file.name }}
                <button type="button" class="font-bold text-red-500" @click="removePhoto(i)">&times;</button>
              </div>
            </div>
          </div>
          <div class="flex justify-end gap-3">
            <button
              type="button"
              class="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-600 hover:border-slate-400"
              @click="showForm = false"
            >
              Cancel
            </button>
            <button
              type="submit"
              :disabled="saving"
              class="rounded-md bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 hover:bg-gold-400 disabled:opacity-60"
            >
              {{ saving ? 'Submitting…' : 'Submit Ticket' }}
            </button>
          </div>
        </form>
      </div>

      <p v-if="loading" class="mt-10 text-center text-slate-500">Loading...</p>
      <p v-else-if="error" class="mt-10 text-center text-red-600">{{ error }}</p>
      <p v-else-if="!tickets.length" class="mt-10 text-center text-slate-500">You haven't filed any support tickets.</p>

      <div v-else class="mt-8 space-y-4">
        <div v-for="ticket in tickets" :key="ticket.id" class="rounded-xl border border-slate-200 bg-slate-50 p-5">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 class="font-[Georgia] text-lg font-bold text-navy-900">{{ ticket.subject }}</h3>
              <p class="text-sm text-slate-500">
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
          <p class="mt-3 whitespace-pre-line text-sm text-slate-700">{{ ticket.description }}</p>
          <div v-if="ticket.photos.length" class="mt-3 flex flex-wrap gap-2">
            <a v-for="photo in ticket.photos" :key="photo.id" :href="photo.image" target="_blank" rel="noopener">
              <img
                :src="photo.image"
                alt="Attached photo"
                class="h-16 w-16 rounded-lg border border-slate-200 object-cover"
              />
            </a>
          </div>

          <div v-if="ticket.status === 'resolved'" class="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-emerald-700">Resolution</p>
            <p class="mt-1 whitespace-pre-line text-sm text-emerald-900">{{ ticket.resolution_note }}</p>
            <button
              :disabled="reopeningId === ticket.id"
              class="mt-3 rounded-md border border-emerald-600 px-3 py-1.5 text-xs font-semibold text-emerald-700 transition hover:bg-emerald-600 hover:text-white disabled:opacity-60"
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
