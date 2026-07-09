<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const isSuperAdmin = computed(() => !!auth.user?.is_superuser)

const { items: announcements, loading, error, load } = useAdminList('/admin/announcements/')
const busyId = ref(null)

const audienceLabels = {
  staff: 'Staff',
  drivers: 'Drivers',
  clients: 'Clients',
}

const statusLabels = {
  pending: 'Pending review',
  approved: 'Approved',
  rejected: 'Rejected',
}

const pending = computed(() => announcements.value.filter((a) => a.status === 'pending'))
const decided = computed(() => announcements.value.filter((a) => a.status !== 'pending'))

const showModal = ref(false)
const saving = ref(false)
const formError = ref('')
const form = reactive({
  title: '',
  body: '',
  audience: 'clients',
})

function openAddModal() {
  Object.assign(form, { title: '', body: '', audience: 'clients' })
  formError.value = ''
  showModal.value = true
}

async function saveAnnouncement() {
  formError.value = ''
  if (!form.title.trim() || !form.body.trim()) {
    formError.value = 'Title and message are required.'
    return
  }
  saving.value = true
  try {
    const { data } = await apiClient.post('/admin/announcements/', form)
    announcements.value.unshift(data)
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    formError.value = typeof detail === 'object'
      ? Object.values(detail).flat().join(' ')
      : 'Could not send this announcement.'
  } finally {
    saving.value = false
  }
}

async function toggleActive(announcement) {
  busyId.value = announcement.id
  try {
    const { data } = await apiClient.patch(`/admin/announcements/${announcement.id}/`, {
      is_active: !announcement.is_active,
    })
    Object.assign(announcement, data)
  } catch {
    error.value = 'Could not update this announcement.'
  } finally {
    busyId.value = null
  }
}

async function deleteAnnouncement(announcement) {
  if (!confirm(`Delete "${announcement.title}"? This cannot be undone.`)) return
  busyId.value = announcement.id
  try {
    await apiClient.delete(`/admin/announcements/${announcement.id}/`)
    announcements.value = announcements.value.filter((a) => a.id !== announcement.id)
  } catch {
    error.value = 'Could not delete this announcement.'
  } finally {
    busyId.value = null
  }
}

async function approve(announcement) {
  busyId.value = announcement.id
  try {
    const { data } = await apiClient.post(`/admin/announcements/${announcement.id}/approve/`)
    Object.assign(announcement, data)
  } catch {
    error.value = 'Could not approve this announcement.'
  } finally {
    busyId.value = null
  }
}

async function reject(announcement) {
  const review_note = prompt(`Reason for rejecting "${announcement.title}" (shown to the submitter, optional):`, '')
  if (review_note === null) return
  busyId.value = announcement.id
  try {
    const { data } = await apiClient.post(`/admin/announcements/${announcement.id}/reject/`, { review_note })
    Object.assign(announcement, data)
  } catch {
    error.value = 'Could not reject this announcement.'
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
    <div class="flex items-center justify-between">
      <div>
        <h1 class="font-[Georgia] text-2xl font-bold text-white">Announcements</h1>
        <p class="mt-1 text-sm text-slate-400">
          <template v-if="isSuperAdmin">
            Broadcast an in-app message to staff, drivers, or clients. No email is sent - they'll
            see it the next time they're in the app.
          </template>
          <template v-else>
            Propose an in-app message to clients. A super admin reviews it before it goes out.
          </template>
        </p>
      </div>
      <button
        class="flex items-center gap-2 rounded-lg bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400"
        @click="openAddModal"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        {{ isSuperAdmin ? 'New Announcement' : 'Propose Announcement' }}
      </button>
    </div>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <template v-if="!loading">
      <!-- Pending approval queue - only superadmins act on these; staff just see their own below. -->
      <div v-if="isSuperAdmin && pending.length" class="mt-6">
        <h2 class="text-xs font-semibold uppercase tracking-wide text-gold-400">Pending Approval</h2>
        <div class="mt-2 space-y-3">
          <div
            v-for="announcement in pending"
            :key="announcement.id"
            class="rounded-xl border border-gold-500/40 bg-navy-900 p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="flex items-center gap-2">
                  <p class="font-semibold text-white">{{ announcement.title }}</p>
                  <span class="rounded-full bg-gold-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gold-400">
                    {{ statusLabels[announcement.status] }}
                  </span>
                </div>
                <p class="mt-1 whitespace-pre-line text-sm text-slate-300">{{ announcement.body }}</p>
                <p class="mt-2 text-xs text-slate-500">
                  Proposed by {{ announcement.created_by_name || 'Unknown' }} &middot;
                  {{ new Date(announcement.created_at).toLocaleString() }}
                </p>
              </div>
              <div class="flex shrink-0 gap-2">
                <button
                  :disabled="busyId === announcement.id"
                  class="rounded-md border border-green-400 px-2 py-1 text-xs font-semibold text-green-400 hover:bg-green-400 hover:text-navy-950 disabled:opacity-50"
                  @click="approve(announcement)"
                >
                  Approve
                </button>
                <button
                  :disabled="busyId === announcement.id"
                  class="rounded-md border border-red-400 px-2 py-1 text-xs font-semibold text-red-400 hover:bg-red-400 hover:text-navy-950 disabled:opacity-50"
                  @click="reject(announcement)"
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-6 space-y-3">
        <h2 v-if="isSuperAdmin && pending.length" class="text-xs font-semibold uppercase tracking-wide text-slate-500">All Announcements</h2>
        <div
          v-for="announcement in (isSuperAdmin ? decided : announcements)"
          :key="announcement.id"
          class="rounded-xl border p-4"
          :class="announcement.is_active ? 'border-navy-800 bg-navy-900' : 'border-navy-800 bg-navy-950 opacity-60'"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="flex items-center gap-2">
                <p class="font-semibold text-white">{{ announcement.title }}</p>
                <span class="rounded-full bg-navy-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gold-400">
                  {{ audienceLabels[announcement.audience] }}
                </span>
                <span
                  v-if="announcement.status !== 'approved'"
                  class="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                  :class="announcement.status === 'rejected' ? 'bg-red-500/10 text-red-400' : 'bg-gold-500/10 text-gold-400'"
                >
                  {{ statusLabels[announcement.status] }}
                </span>
                <span v-else-if="!announcement.is_active" class="rounded-full bg-navy-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  Inactive
                </span>
              </div>
              <p class="mt-1 whitespace-pre-line text-sm text-slate-300">{{ announcement.body }}</p>
              <p v-if="announcement.status === 'rejected' && announcement.review_note" class="mt-2 text-xs text-red-400">
                Reason: {{ announcement.review_note }}
              </p>
              <p class="mt-2 text-xs text-slate-500">
                {{ announcement.created_by_name || 'Unknown' }} &middot;
                {{ new Date(announcement.created_at).toLocaleString() }}
                <template v-if="announcement.reviewed_by_name">
                  &middot; reviewed by {{ announcement.reviewed_by_name }}
                </template>
              </p>
            </div>
            <div v-if="isSuperAdmin" class="flex shrink-0 gap-2">
              <button
                :disabled="busyId === announcement.id"
                class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="toggleActive(announcement)"
              >
                {{ announcement.is_active ? 'Deactivate' : 'Activate' }}
              </button>
              <button
                :disabled="busyId === announcement.id"
                class="rounded-md border border-red-400 px-2 py-1 text-xs font-semibold text-red-400 hover:bg-red-400 hover:text-navy-950 disabled:opacity-50"
                @click="deleteAnnouncement(announcement)"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
        <p v-if="!announcements.length" class="p-6 text-center text-slate-400">
          {{ isSuperAdmin ? 'No announcements yet.' : "You haven't proposed any announcements yet." }}
        </p>
      </div>
    </template>

    <!-- New Announcement Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-lg rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">
                {{ isSuperAdmin ? 'New Announcement' : 'Propose Announcement to Clients' }}
              </h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="!isSuperAdmin" class="mb-4 rounded-lg bg-navy-800 px-4 py-3 text-sm text-slate-300">
              This will be sent to clients once a super admin approves it.
            </p>
            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ formError }}</p>

            <form class="space-y-4" @submit.prevent="saveAnnouncement">
              <div v-if="isSuperAdmin">
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Send To</label>
                <select v-model="form.audience"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none">
                  <option value="clients">Clients</option>
                  <option value="drivers">Drivers</option>
                  <option value="staff">Staff</option>
                </select>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Title *</label>
                <input
                  v-model="form.title" type="text" placeholder="e.g. Scheduled maintenance tonight" required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Message *</label>
                <textarea
                  v-model="form.body" rows="4" required placeholder="What do they need to know?"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                ></textarea>
              </div>

              <div class="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  class="rounded-lg border border-navy-700 px-4 py-2 text-sm font-medium text-slate-300 hover:text-white"
                  @click="showModal = false"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  :disabled="saving"
                  class="rounded-lg bg-gold-500 px-5 py-2 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400 disabled:opacity-50"
                >
                  {{ saving ? 'Sending…' : (isSuperAdmin ? 'Send Announcement' : 'Submit for Approval') }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
