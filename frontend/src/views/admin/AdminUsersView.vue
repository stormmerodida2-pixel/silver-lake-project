<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const { items: users, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/users/')
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

// ── Existing actions ────────────────────────────────────────────────────────
async function toggleActive(user) {
  busyId.value = user.id
  try {
    const action = user.is_active ? 'suspend' : 'activate'
    const { data } = await apiClient.post(`/admin/users/${user.id}/${action}/`)
    Object.assign(user, data)
  } catch (err) {
    error.value = 'Could not update this user.'
  } finally {
    busyId.value = null
  }
}

async function deleteUser(user) {
  if (!confirm(`Delete ${user.email}? This cannot be undone.`)) return
  busyId.value = user.id
  try {
    await apiClient.delete(`/admin/users/${user.id}/`)
    users.value = users.value.filter((u) => u.id !== user.id)
  } catch (err) {
    error.value = 'Could not delete this user.'
  } finally {
    busyId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h1 class="font-[Georgia] text-2xl font-bold text-white">Manage Users</h1>
      <button
        v-if="auth.user?.is_superuser"
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
            <td class="px-4 py-3">
              <span :class="user.is_active ? 'text-gold-400' : 'text-red-400'">
                {{ user.is_active ? 'Active' : 'Suspended' }}
              </span>
            </td>
            <td class="px-4 py-3 text-slate-400">{{ new Date(user.date_joined).toLocaleDateString() }}</td>
            <td class="space-x-2 whitespace-nowrap px-4 py-3">
              <button
                :disabled="busyId === user.id"
                class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="toggleActive(user)"
              >
                {{ user.is_active ? 'Suspend' : 'Activate' }}
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
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-md rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <!-- Modal header -->
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">Add New User</h2>
              <button
                class="text-slate-400 transition-colors hover:text-white"
                @click="showModal = false"
              >
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
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Email Address *</label>
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
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Phone Number</label>
                <input
                  id="new-user-phone"
                  v-model="form.phone_number"
                  type="tel"
                  placeholder="+254 700 000 000"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none focus:ring-1 focus:ring-gold-500"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Password *</label>
                <input
                  id="new-user-password"
                  v-model="form.password"
                  type="password"
                  placeholder="Minimum 8 characters"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none focus:ring-1 focus:ring-gold-500"
                  required
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Confirm Password *</label>
                <input
                  id="new-user-confirm-password"
                  v-model="form.confirm_password"
                  type="password"
                  placeholder="Repeat password"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none focus:ring-1 focus:ring-gold-500"
                  required
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
