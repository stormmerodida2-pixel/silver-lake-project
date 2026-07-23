<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import apiClient from '../../api/client'
import PasswordInput from '../../components/PasswordInput.vue'
import PhoneInput from '../../components/PhoneInput.vue'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'
import { confirmDialog } from '../../utils/dialogs'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const filters = reactive({ search: '', role: '' })
const { items: users, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/users/', filters)
const busyId = ref(null)

// ── Add-User modal ──────────────────────────────────────────────────────────
const showModal = ref(false)
const saving = ref(false)
const formError = ref('')
const form = reactive({ full_name: '', email: '', phone_number: '', password: '', confirm_password: '' })

function openModal() {
  Object.assign(form, { full_name: '', email: '', phone_number: '', password: '', confirm_password: '' })
  formError.value = ''
  showModal.value = true
}

async function createUser() {
  formError.value = ''
  if (!form.full_name || !form.email || !form.password) {
    formError.value = 'Full name, email, and password are required.'
    return
  }
  if (form.password !== form.confirm_password) {
    formError.value = 'Passwords do not match.'
    return
  }
  saving.value = true
  try {
    const { data } = await apiClient.post('/admin/users/', {
      full_name: form.full_name,
      email: form.email,
      phone_number: form.phone_number,
      password: form.password,
    })
    users.value.unshift(data)
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    if (typeof detail === 'object') {
      formError.value = Object.values(detail).flat().join(' ')
    } else {
      formError.value = 'Could not create user. Please try again.'
    }
  } finally {
    saving.value = false
  }
}

// ── Invite Staff modal ───────────────────────────────────────────────────────
const showInviteModal = ref(false)
const inviting = ref(false)
const inviteError = ref('')
const inviteForm = reactive({ first_name: '', last_name: '', email: '', is_superuser: false })

function openInviteModal() {
  Object.assign(inviteForm, { first_name: '', last_name: '', email: '', is_superuser: false })
  inviteError.value = ''
  showInviteModal.value = true
}

async function inviteStaff() {
  inviteError.value = ''
  if (!inviteForm.email) {
    inviteError.value = 'Email is required.'
    return
  }
  inviting.value = true
  try {
    const { data } = await apiClient.post('/admin/users/invite-staff/', inviteForm)
    users.value.unshift(data)
    showInviteModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    inviteError.value =
      typeof detail === 'object'
        ? Object.values(detail).flat().join(' ')
        : 'Could not send this invite. Please try again.'
  } finally {
    inviting.value = false
  }
}

// ── Existing actions ────────────────────────────────────────────────────────
async function toggleActive(user) {
  busyId.value = user.id
  try {
    const action = user.is_active ? 'suspend' : 'activate'
    const { data } = await apiClient.post(`/admin/users/${user.id}/${action}/`)
    Object.assign(user, data)
  } catch {
    error.value = 'Could not update this user.'
  } finally {
    busyId.value = null
  }
}

async function impersonate(user) {
  if (
    !(await confirmDialog(`View the app as ${user.email}? You'll act as this customer until you stop impersonating.`))
  )
    return
  busyId.value = user.id
  try {
    await auth.startImpersonation(user.id, route.fullPath)
    router.push('/')
  } catch {
    error.value = 'Could not start impersonating this user.'
  } finally {
    busyId.value = null
  }
}

async function deleteUser(user) {
  if (!(await confirmDialog(`Delete ${user.email}? This cannot be undone.`, { danger: true }))) return
  busyId.value = user.id
  try {
    await apiClient.delete(`/admin/users/${user.id}/`)
    users.value = users.value.filter((u) => u.id !== user.id)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not delete this user.'
  } finally {
    busyId.value = null
  }
}

// ── Edit-User modal ──────────────────────────────────────────────────────────
const showEditModal = ref(false)
const editSaving = ref(false)
const editError = ref('')
const editingUser = ref(null)
const editForm = reactive({
  first_name: '',
  last_name: '',
  phone_number: '',
  is_active: true,
  is_staff: false,
  is_superuser: false,
})

function openEditModal(user) {
  editingUser.value = user
  Object.assign(editForm, {
    first_name: user.first_name,
    last_name: user.last_name,
    phone_number: user.phone_number || '',
    is_active: user.is_active,
    is_staff: user.is_staff,
    is_superuser: user.is_superuser,
  })
  editError.value = ''
  showEditModal.value = true
}

async function saveUser() {
  editError.value = ''
  editSaving.value = true
  try {
    const { data } = await apiClient.patch(`/admin/users/${editingUser.value.id}/`, editForm)
    Object.assign(editingUser.value, data)
    showEditModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    if (typeof detail === 'object') {
      editError.value = Object.values(detail).flat().join(' ')
    } else {
      editError.value = 'Could not update this user.'
    }
  } finally {
    editSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="font-[Georgia] text-2xl font-bold text-white">Manage Users</h1>
        <p v-if="auth.user?.organization_name" class="mt-1 text-sm text-slate-400">
          Showing {{ auth.user.organization_name }}'s own staff only.
        </p>
      </div>
      <div v-if="auth.user?.is_superuser" class="flex gap-2">
        <button
          class="flex items-center gap-2 rounded-lg border border-navy-700 px-4 py-2 text-sm font-semibold text-slate-300 transition-colors hover:border-gold-400 hover:text-gold-400"
          @click="openInviteModal"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M16 12a4 4 0 1 0-8 0 4 4 0 0 0 8 0Zm-8 8a6 6 0 0 1 12 0M20 8v6M23 11h-6"
            />
          </svg>
          Invite Staff
        </button>
        <button
          id="add-user-btn"
          class="flex items-center gap-2 rounded-lg bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400"
          @click="openModal"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Add User
        </button>
      </div>
    </div>

    <div class="mt-4 flex flex-wrap gap-3">
      <input
        v-model="filters.search"
        type="text"
        placeholder="Search by name or email..."
        class="min-w-64 flex-1 rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-gold-400 focus:outline-none"
      />
      <select
        v-model="filters.role"
        class="rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-sm text-white focus:border-gold-400 focus:outline-none"
      >
        <option value="">All roles</option>
        <option value="customer">Customer</option>
        <option value="staff">Support Staff</option>
        <option value="superadmin">{{ auth.user?.organization_name ? 'Org Admin' : 'Super Admin' }}</option>
      </select>
    </div>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <div v-if="!loading" class="mt-6 overflow-x-auto rounded-xl border border-navy-800">
      <table class="w-full text-left text-sm">
        <thead class="bg-navy-900 text-slate-400">
          <tr>
            <th class="px-4 py-3">Name</th>
            <th class="px-4 py-3">Email</th>
            <th class="px-4 py-3">Phone</th>
            <th class="px-4 py-3">Bookings</th>
            <th class="px-4 py-3">Role</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Joined</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-navy-800 bg-navy-950">
          <tr v-for="user in users" :key="user.id">
            <td class="px-4 py-3 text-white">{{ user.first_name }} {{ user.last_name }}</td>
            <td class="px-4 py-3 text-slate-300">{{ user.email }}</td>
            <td class="px-4 py-3 text-slate-300">{{ user.phone_number || '-' }}</td>
            <td class="px-4 py-3 text-slate-300">{{ user.bookings_count }}</td>
            <td class="px-4 py-3 text-slate-300">
              <span v-if="user.is_superuser" class="text-gold-400">{{
                user.organization_name ? 'Org Admin' : 'Super Admin'
              }}</span>
              <span v-else-if="user.is_staff">Support Staff</span>
              <span v-else>Customer</span>
              <div v-if="user.organization_name" class="text-xs text-slate-500">{{ user.organization_name }}</div>
            </td>
            <td class="px-4 py-3">
              <span
                class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold"
                :class="user.is_active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'"
              >
                <span class="h-1.5 w-1.5 rounded-full" :class="user.is_active ? 'bg-emerald-400' : 'bg-red-400'" />
                {{ user.is_active ? 'Active' : 'Suspended' }}
              </span>
            </td>
            <td class="px-4 py-3 text-slate-400">{{ new Date(user.date_joined).toLocaleDateString() }}</td>
            <td class="space-x-2 whitespace-nowrap px-4 py-3">
              <button
                v-if="auth.user?.is_superuser"
                class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400"
                @click="openEditModal(user)"
              >
                Edit
              </button>
              <button
                :disabled="busyId === user.id"
                class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="toggleActive(user)"
              >
                {{ user.is_active ? 'Suspend' : 'Activate' }}
              </button>
              <button
                v-if="auth.user?.is_superuser && !auth.user?.organization_name && !user.is_staff"
                :disabled="busyId === user.id"
                title="View the app as this customer, for support/debugging"
                class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="impersonate(user)"
              >
                Impersonate
              </button>
              <button
                v-if="auth.user?.is_superuser"
                :disabled="busyId === user.id"
                class="rounded-md border border-red-400 px-2 py-1 text-xs font-semibold text-red-400 hover:bg-red-400 hover:text-navy-950 disabled:opacity-50"
                @click="deleteUser(user)"
              >
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!users.length" class="p-6 text-center text-slate-400">No customer accounts yet.</p>
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

    <!-- Add User Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showModal"
          id="add-user-modal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-md rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <!-- Modal header -->
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">Add New User</h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <!-- Error -->
            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {{ formError }}
            </p>

            <!-- Form -->
            <form class="space-y-4" @submit.prevent="createUser">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Full Name *</label>
                <input
                  id="new-user-full-name"
                  v-model="form.full_name"
                  type="text"
                  placeholder="Jane Doe"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none focus:ring-1 focus:ring-gold-500"
                  required
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                  >Email Address *</label
                >
                <input
                  id="new-user-email"
                  v-model="form.email"
                  type="email"
                  placeholder="jane@example.com"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none focus:ring-1 focus:ring-gold-500"
                  required
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                  >Phone Number</label
                >
                <PhoneInput v-model="form.phone_number" dark />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Password *</label>
                <PasswordInput
                  v-model="form.password"
                  required
                  placeholder="Minimum 8 characters"
                  input-class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none focus:ring-1 focus:ring-gold-500"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                  >Confirm Password *</label
                >
                <PasswordInput
                  v-model="form.confirm_password"
                  required
                  placeholder="Repeat password"
                  input-class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none focus:ring-1 focus:ring-gold-500"
                />
              </div>

              <p class="text-xs text-slate-500">
                The account will be created as <span class="text-gold-400">Active</span> — no email verification needed.
              </p>

              <div class="flex gap-3 pt-2">
                <button
                  type="button"
                  class="flex-1 rounded-lg border border-navy-700 py-2.5 text-sm font-semibold text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
                  @click="showModal = false"
                >
                  Cancel
                </button>
                <button
                  id="create-user-submit"
                  type="submit"
                  :disabled="saving"
                  class="flex-1 rounded-lg bg-gold-500 py-2.5 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400 disabled:opacity-50"
                >
                  {{ saving ? 'Creating…' : 'Create User' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Edit User Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showEditModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showEditModal = false"
        >
          <div class="w-full max-w-md rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">Edit User</h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showEditModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="editError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {{ editError }}
            </p>

            <form class="space-y-4" @submit.prevent="saveUser">
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                    >First Name</label
                  >
                  <input
                    v-model="editForm.first_name"
                    type="text"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none focus:ring-1 focus:ring-gold-500"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Last Name</label>
                  <input
                    v-model="editForm.last_name"
                    type="text"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none focus:ring-1 focus:ring-gold-500"
                  />
                </div>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Email</label>
                <input
                  :value="editingUser?.email"
                  type="email"
                  disabled
                  class="w-full cursor-not-allowed rounded-lg border border-navy-700 bg-navy-800/50 px-4 py-2.5 text-sm text-slate-500"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                  >Phone Number</label
                >
                <PhoneInput v-model="editForm.phone_number" dark />
              </div>

              <label class="flex items-center gap-2 text-sm text-slate-300">
                <input
                  v-model="editForm.is_active"
                  type="checkbox"
                  class="h-4 w-4 rounded border-navy-700 bg-navy-800"
                />
                Active
              </label>

              <div class="rounded-lg border border-navy-700 bg-navy-800/50 p-4">
                <p class="mb-2 text-xs font-semibold uppercase tracking-wide text-gold-400">Admin Role</p>
                <label class="flex items-center gap-2 text-sm text-slate-300">
                  <input
                    v-model="editForm.is_staff"
                    type="checkbox"
                    class="h-4 w-4 rounded border-navy-700 bg-navy-800"
                  />
                  Support Staff (dashboard access)
                </label>
                <label class="mt-2 flex items-center gap-2 text-sm text-slate-300">
                  <input
                    v-model="editForm.is_superuser"
                    type="checkbox"
                    class="h-4 w-4 rounded border-navy-700 bg-navy-800"
                  />
                  Super Admin (full access, incl. destructive actions)
                </label>
              </div>

              <div class="flex gap-3 pt-2">
                <button
                  type="button"
                  class="flex-1 rounded-lg border border-navy-700 py-2.5 text-sm font-semibold text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
                  @click="showEditModal = false"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  :disabled="editSaving"
                  class="flex-1 rounded-lg bg-gold-500 py-2.5 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400 disabled:opacity-50"
                >
                  {{ editSaving ? 'Saving…' : 'Save Changes' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Invite Staff Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showInviteModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showInviteModal = false"
        >
          <div class="w-full max-w-md rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">Invite Staff</h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showInviteModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="inviteError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {{ inviteError }}
            </p>

            <form class="space-y-4" @submit.prevent="inviteStaff">
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                    >First Name</label
                  >
                  <input
                    v-model="inviteForm.first_name"
                    type="text"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Last Name</label>
                  <input
                    v-model="inviteForm.last_name"
                    type="text"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                  />
                </div>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Email *</label>
                <input
                  v-model="inviteForm.email"
                  type="email"
                  placeholder="jane@example.com"
                  required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                />
              </div>
              <label class="flex items-center gap-2 text-sm text-slate-300">
                <input
                  v-model="inviteForm.is_superuser"
                  type="checkbox"
                  class="h-4 w-4 rounded border-navy-700 bg-navy-800"
                />
                {{
                  auth.user?.organization_name
                    ? `Give full admin access to ${auth.user.organization_name}`
                    : 'Super Admin (full platform access)'
                }}
              </label>
              <p class="text-xs text-slate-500">
                They'll get an email with a link to set their own password - nothing is emailed in plain text.
                <template v-if="auth.user?.organization_name"
                  >Scoped to {{ auth.user.organization_name }} only.</template
                >
              </p>

              <div class="flex gap-3 pt-2">
                <button
                  type="button"
                  class="flex-1 rounded-lg border border-navy-700 py-2.5 text-sm font-semibold text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
                  @click="showInviteModal = false"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  :disabled="inviting"
                  class="flex-1 rounded-lg bg-gold-500 py-2.5 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400 disabled:opacity-50"
                >
                  {{ inviting ? 'Sending…' : 'Send Invite' }}
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
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
