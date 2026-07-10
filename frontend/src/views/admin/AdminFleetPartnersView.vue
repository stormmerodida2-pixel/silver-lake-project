<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'

const { items: partners, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/fleet-partners/')
const busyId = ref(null)

const showModal = ref(false)
const editingId = ref(null) // null = create, number = edit
const saving = ref(false)
const formError = ref('')
const form = reactive({
  name: '',
  contact_email: '',
  contact_phone: '',
  platform_fee_percent: '10',
})

const modalTitle = () => editingId.value ? 'Edit Fleet Partner' : 'Register Fleet Partner'
const submitLabel = () => saving.value
  ? (editingId.value ? 'Saving…' : 'Registering…')
  : (editingId.value ? 'Save Changes' : 'Register Partner')

function resetForm() {
  Object.assign(form, { name: '', contact_email: '', contact_phone: '', platform_fee_percent: '10' })
}

function openAddModal() {
  editingId.value = null
  resetForm()
  formError.value = ''
  showModal.value = true
}

function openEditModal(partner) {
  editingId.value = partner.id
  Object.assign(form, {
    name: partner.name, contact_email: partner.contact_email, contact_phone: partner.contact_phone,
    platform_fee_percent: partner.platform_fee_percent,
  })
  formError.value = ''
  showModal.value = true
}

async function savePartner() {
  formError.value = ''
  if (!form.name.trim()) {
    formError.value = 'Name is required.'
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      const { data } = await apiClient.patch(`/admin/fleet-partners/${editingId.value}/`, form)
      const idx = partners.value.findIndex((p) => p.id === editingId.value)
      if (idx !== -1) partners.value[idx] = data
    } else {
      const { data } = await apiClient.post('/admin/fleet-partners/', form)
      partners.value.unshift(data)
    }
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    formError.value = typeof detail === 'object'
      ? Object.values(detail).flat().join(' ')
      : 'Could not save this partner. Please try again.'
  } finally {
    saving.value = false
  }
}

async function toggleActive(partner) {
  busyId.value = partner.id
  try {
    const { data } = await apiClient.patch(`/admin/fleet-partners/${partner.id}/`, { is_active: !partner.is_active })
    Object.assign(partner, data)
  } catch {
    error.value = 'Could not update this partner.'
  } finally {
    busyId.value = null
  }
}

async function deletePartner(partner) {
  if (!confirm(`Delete "${partner.name}"? This cannot be undone.`)) return
  busyId.value = partner.id
  try {
    await apiClient.delete(`/admin/fleet-partners/${partner.id}/`)
    partners.value = partners.value.filter((p) => p.id !== partner.id)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not delete this partner.'
  } finally {
    busyId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between">
      <div>
        <h1 class="font-[Georgia] text-2xl font-bold text-white">Fleet Partners</h1>
        <p class="mt-1 text-sm text-slate-400">
          Companies that have registered their own fleet with SilverLake - assign their vehicles
          to them under Admin → Fleet. SilverLake only takes the platform fee below; the rest is
          the partner's own money.
        </p>
      </div>
      <button
        class="flex shrink-0 items-center gap-2 rounded-lg bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400"
        @click="openAddModal"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        Register Partner
      </button>
    </div>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <div v-if="!loading" class="mt-6 overflow-x-auto rounded-xl border border-navy-800">
      <table class="w-full text-left text-sm">
        <thead class="bg-navy-900 text-slate-400">
          <tr>
            <th class="px-4 py-3">Partner</th>
            <th class="px-4 py-3">Contact</th>
            <th class="px-4 py-3">Platform Fee</th>
            <th class="px-4 py-3">Vehicles</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-navy-800 bg-navy-950">
          <tr v-for="partner in partners" :key="partner.id">
            <td class="px-4 py-3 font-medium text-white">{{ partner.name }}</td>
            <td class="px-4 py-3 text-xs text-slate-400">
              <div>{{ partner.contact_email || '—' }}</div>
              <div>{{ partner.contact_phone }}</div>
            </td>
            <td class="px-4 py-3 text-slate-300">{{ partner.platform_fee_percent }}%</td>
            <td class="px-4 py-3 text-slate-300">{{ partner.vehicle_count }}</td>
            <td class="px-4 py-3">
              <span :class="partner.is_active ? 'text-gold-400' : 'text-slate-500'">
                {{ partner.is_active ? 'Active' : 'Inactive' }}
              </span>
            </td>
            <td class="space-x-2 whitespace-nowrap px-4 py-3">
              <button
                :disabled="busyId === partner.id"
                class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="openEditModal(partner)"
              >
                Edit
              </button>
              <button
                :disabled="busyId === partner.id"
                class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="toggleActive(partner)"
              >
                {{ partner.is_active ? 'Deactivate' : 'Activate' }}
              </button>
              <button
                :disabled="busyId === partner.id"
                class="rounded-md border border-red-400 px-2 py-1 text-xs font-semibold text-red-400 hover:bg-red-400 hover:text-navy-950 disabled:opacity-50"
                @click="deletePartner(partner)"
              >
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!partners.length" class="p-6 text-center text-slate-400">No fleet partners registered yet.</p>
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

    <!-- Add / Edit Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-lg rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">{{ modalTitle() }}</h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ formError }}</p>

            <form class="space-y-4" @submit.prevent="savePartner">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Company Name *</label>
                <input
                  v-model="form.name" type="text" placeholder="e.g. Coastline Rentals Ltd" required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Contact Email</label>
                  <input
                    v-model="form.contact_email" type="email" placeholder="ops@partner.co.ke"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Contact Phone</label>
                  <input
                    v-model="form.contact_phone" type="text" placeholder="2547XXXXXXXX"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Platform Fee (%)</label>
                <input
                  v-model="form.platform_fee_percent" type="number" min="0" max="100" step="0.01"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                />
                <p class="mt-1 text-xs text-slate-500">
                  SilverLake's cut, kept as revenue. The rest is owed back to this partner via a
                  normal payout (Admin → Payouts) once a booking on their vehicle is fully paid -
                  every payment still goes through SilverLake's own Paybill, not the partner's.
                </p>
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
                  {{ submitLabel() }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active { transition: opacity 0.2s ease; }
.modal-fade-enter-from,
.modal-fade-leave-to { opacity: 0; }
</style>
