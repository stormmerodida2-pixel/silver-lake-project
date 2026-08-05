<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { confirmDialog } from '../../utils/dialogs'

const { items: tiers, loading, error, load } = useAdminList('/admin/loyalty-tiers/')
const busyId = ref(null)

const showModal = ref(false)
const editingId = ref(null)
const saving = ref(false)
const formError = ref('')
const form = reactive({ name: '', min_completed_trips: '', discount_percent: '' })

function openAddModal() {
  editingId.value = null
  Object.assign(form, { name: '', min_completed_trips: '', discount_percent: '' })
  formError.value = ''
  showModal.value = true
}

function openEditModal(tier) {
  editingId.value = tier.id
  Object.assign(form, {
    name: tier.name,
    min_completed_trips: tier.min_completed_trips,
    discount_percent: tier.discount_percent,
  })
  formError.value = ''
  showModal.value = true
}

async function saveTier() {
  formError.value = ''
  saving.value = true
  const payload = {
    name: form.name.trim(),
    min_completed_trips: form.min_completed_trips,
    discount_percent: form.discount_percent,
  }
  try {
    if (editingId.value) {
      const { data } = await apiClient.patch(`/admin/loyalty-tiers/${editingId.value}/`, payload)
      const index = tiers.value.findIndex((t) => t.id === editingId.value)
      tiers.value[index] = data
    } else {
      const { data } = await apiClient.post('/admin/loyalty-tiers/', payload)
      tiers.value.push(data)
      tiers.value.sort((a, b) => a.min_completed_trips - b.min_completed_trips)
    }
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    formError.value = typeof detail === 'object' ? Object.values(detail).flat().join(' ') : 'Could not save this tier.'
  } finally {
    saving.value = false
  }
}

async function deleteTier(tier) {
  if (!(await confirmDialog(`Delete the "${tier.name}" tier? This cannot be undone.`, { danger: true }))) return
  busyId.value = tier.id
  try {
    await apiClient.delete(`/admin/loyalty-tiers/${tier.id}/`)
    tiers.value = tiers.value.filter((t) => t.id !== tier.id)
  } catch {
    error.value = 'Could not delete this tier.'
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
        <h1 class="font-[Georgia] text-2xl font-bold text-foreground">Loyalty Tiers</h1>
        <p class="mt-1 text-sm text-foreground-muted">
          A customer's tier is based on their own lifetime completed trips, and its discount applies automatically to
          every booking they make from then on - no code needed.
        </p>
      </div>
      <button
        class="flex shrink-0 items-center gap-2 rounded-lg bg-accent-bg px-4 py-2 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-bg-hover"
        @click="openAddModal"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        Add Tier
      </button>
    </div>

    <p v-if="loading" class="mt-10 text-center text-foreground-muted">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-danger">{{ error }}</p>

    <div v-if="!loading" class="mt-6 space-y-3">
      <div v-for="tier in tiers" :key="tier.id" class="rounded-xl border border-border-subtle bg-surface p-4">
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-bg/10 text-accent">
              <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674Z"
                />
              </svg>
            </span>
            <div>
              <p class="font-semibold text-foreground">{{ tier.name }}</p>
              <p class="text-xs text-foreground-subtle">
                {{ tier.min_completed_trips }}+ completed trips &middot; {{ Number(tier.discount_percent) }}% off every
                booking
              </p>
            </div>
          </div>
          <div class="flex shrink-0 gap-2">
            <button
              :disabled="busyId === tier.id"
              class="rounded-md border border-border px-2 py-1 text-xs font-semibold text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
              @click="openEditModal(tier)"
            >
              Edit
            </button>
            <button
              :disabled="busyId === tier.id"
              class="rounded-md border border-danger-border px-2 py-1 text-xs font-semibold text-danger hover:bg-red-400 hover:text-on-accent disabled:opacity-50"
              @click="deleteTier(tier)"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
      <p v-if="!tiers.length" class="p-6 text-center text-foreground-muted">No loyalty tiers yet.</p>
    </div>

    <!-- Add/Edit Tier Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-lg rounded-2xl border border-border bg-surface p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-foreground">{{ editingId ? 'Edit Tier' : 'Add Tier' }}</h2>
              <button class="text-foreground-muted transition-colors hover:text-foreground" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-danger">{{ formError }}</p>

            <form class="space-y-4" @submit.prevent="saveTier">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted">Tier Name *</label>
                <input
                  v-model="form.name"
                  type="text"
                  required
                  placeholder="e.g. Gold"
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground placeholder-foreground-subtle focus:border-accent-border-strong focus:outline-none"
                />
              </div>
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                    >Min. Completed Trips *</label
                  >
                  <input
                    v-model="form.min_completed_trips"
                    type="number"
                    min="0"
                    step="1"
                    required
                    placeholder="e.g. 6"
                    class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground placeholder-foreground-subtle focus:border-accent-border-strong focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                    >Discount (%) *</label
                  >
                  <input
                    v-model="form.discount_percent"
                    type="number"
                    min="0"
                    max="100"
                    step="0.01"
                    required
                    placeholder="e.g. 10"
                    class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground placeholder-foreground-subtle focus:border-accent-border-strong focus:outline-none"
                  />
                </div>
              </div>

              <div class="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  class="rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground-secondary hover:text-foreground"
                  @click="showModal = false"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  :disabled="saving"
                  class="rounded-lg bg-accent-bg px-5 py-2 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-bg-hover disabled:opacity-50"
                >
                  {{ saving ? 'Saving…' : 'Save Tier' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
