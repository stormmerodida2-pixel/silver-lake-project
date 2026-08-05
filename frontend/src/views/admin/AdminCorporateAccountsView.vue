<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import PhoneInput from '../../components/PhoneInput.vue'
import { confirmDialog } from '../../utils/dialogs'

const { items: accounts, loading, error, load } = useAdminList('/admin/corporate-accounts/')
const busyId = ref(null)

const showModal = ref(false)
const editingId = ref(null)
const saving = ref(false)
const formError = ref('')
const form = reactive({
  name: '',
  contact_email: '',
  contact_phone: '',
  is_active: true,
})

function openAddModal() {
  editingId.value = null
  Object.assign(form, { name: '', contact_email: '', contact_phone: '', is_active: true })
  formError.value = ''
  showModal.value = true
}

function openEditModal(account) {
  editingId.value = account.id
  Object.assign(form, {
    name: account.name,
    contact_email: account.contact_email,
    contact_phone: account.contact_phone,
    is_active: account.is_active,
  })
  formError.value = ''
  showModal.value = true
}

async function saveAccount() {
  formError.value = ''
  saving.value = true
  const payload = {
    name: form.name.trim(),
    contact_email: form.contact_email.trim(),
    contact_phone: form.contact_phone,
    is_active: form.is_active,
  }
  try {
    if (editingId.value) {
      const { data } = await apiClient.patch(`/admin/corporate-accounts/${editingId.value}/`, payload)
      const index = accounts.value.findIndex((a) => a.id === editingId.value)
      accounts.value[index] = data
    } else {
      const { data } = await apiClient.post('/admin/corporate-accounts/', payload)
      accounts.value.push(data)
      accounts.value.sort((a, b) => a.name.localeCompare(b.name))
    }
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    formError.value =
      typeof detail === 'object' ? Object.values(detail).flat().join(' ') : 'Could not save this account.'
  } finally {
    saving.value = false
  }
}

async function deleteAccount(account) {
  if (!(await confirmDialog(`Delete the "${account.name}" corporate account? This cannot be undone.`, { danger: true })))
    return
  busyId.value = account.id
  try {
    await apiClient.delete(`/admin/corporate-accounts/${account.id}/`)
    accounts.value = accounts.value.filter((a) => a.id !== account.id)
  } catch {
    error.value = 'Could not delete this account - it may still have bookings on file.'
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
        <h1 class="font-[Georgia] text-2xl font-bold text-foreground">Corporate Accounts</h1>
        <p class="mt-1 text-sm text-foreground-muted">
          Private companies billed later via invoice for bookings made on their behalf, the same way a government
          contract is - see Bookings &rarr; "+ Corporate Booking".
        </p>
      </div>
      <button
        class="flex shrink-0 items-center gap-2 rounded-lg bg-accent-bg px-4 py-2 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-bg-hover"
        @click="openAddModal"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        Add Account
      </button>
    </div>

    <p v-if="loading" class="mt-10 text-center text-foreground-muted">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-danger">{{ error }}</p>

    <div v-if="!loading" class="mt-6 space-y-3">
      <div v-for="account in accounts" :key="account.id" class="rounded-xl border border-border-subtle bg-surface p-4">
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-bg/10 text-accent">
              <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"
                />
              </svg>
            </span>
            <div>
              <p class="flex items-center gap-2 font-semibold text-foreground">
                {{ account.name }}
                <span
                  v-if="!account.is_active"
                  class="rounded-full bg-slate-700 px-2 py-0.5 text-[10px] font-semibold uppercase text-foreground-secondary"
                >
                  Inactive
                </span>
              </p>
              <p class="text-xs text-foreground-subtle">
                {{ account.booking_count }} booking{{ account.booking_count === 1 ? '' : 's' }}
                <template v-if="account.contact_email"> &middot; {{ account.contact_email }}</template>
                <template v-if="account.contact_phone"> &middot; {{ account.contact_phone }}</template>
              </p>
            </div>
          </div>
          <div class="flex shrink-0 gap-2">
            <button
              :disabled="busyId === account.id"
              class="rounded-md border border-border px-2 py-1 text-xs font-semibold text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
              @click="openEditModal(account)"
            >
              Edit
            </button>
            <button
              :disabled="busyId === account.id"
              class="rounded-md border border-danger-border px-2 py-1 text-xs font-semibold text-danger hover:bg-red-400 hover:text-on-accent disabled:opacity-50"
              @click="deleteAccount(account)"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
      <p v-if="!accounts.length" class="p-6 text-center text-foreground-muted">No corporate accounts yet.</p>
    </div>

    <!-- Add/Edit Account Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-lg rounded-2xl border border-border bg-surface p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-foreground">
                {{ editingId ? 'Edit Account' : 'Add Account' }}
              </h2>
              <button class="text-foreground-muted transition-colors hover:text-foreground" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-danger">{{ formError }}</p>

            <form class="space-y-4" @submit.prevent="saveAccount">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                  >Company Name *</label
                >
                <input
                  v-model="form.name"
                  type="text"
                  required
                  placeholder="e.g. Acme Logistics Ltd"
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground placeholder-foreground-subtle focus:border-accent-border-strong focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                  >Contact Email</label
                >
                <input
                  v-model="form.contact_email"
                  type="email"
                  class="w-full rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm text-foreground placeholder-foreground-subtle focus:border-accent-border-strong focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-foreground-muted"
                  >Contact Phone</label
                >
                <PhoneInput v-model="form.contact_phone" dark />
              </div>
              <label class="flex items-center gap-2 text-sm text-foreground-secondary">
                <input v-model="form.is_active" type="checkbox" class="rounded border-border bg-surface-2" />
                Active (can be billed for new bookings)
              </label>

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
                  {{ saving ? 'Saving…' : 'Save Account' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
