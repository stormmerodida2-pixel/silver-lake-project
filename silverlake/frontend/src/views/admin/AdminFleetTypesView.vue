<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const { items: categories, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/fleet-types/')
const busyId = ref(null)

const showModal = ref(false)
const editingId = ref(null)   // null = create, number = edit
const saving = ref(false)
const formError = ref('')
const form = reactive({
  name: '',
  order: 0,
})

const modalTitle = () => editingId.value ? 'Edit Fleet Type' : 'Add Fleet Type'
const submitLabel = () => saving.value
  ? (editingId.value ? 'Saving…' : 'Creating…')
  : (editingId.value ? 'Save Changes' : 'Add Fleet Type')

function openAddModal() {
  editingId.value = null
  Object.assign(form, { name: '', order: (categories.value.length || 0) })
  formError.value = ''
  showModal.value = true
}

function openEditModal(category) {
  editingId.value = category.id
  Object.assign(form, { name: category.name, order: category.order })
  formError.value = ''
  showModal.value = true
}

async function saveCategory() {
  formError.value = ''
  if (!form.name.trim()) {
    formError.value = 'Name is required.'
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      const { data } = await apiClient.patch(`/admin/fleet-types/${editingId.value}/`, form)
      const idx = categories.value.findIndex((c) => c.id === editingId.value)
      if (idx !== -1) categories.value[idx] = data
    } else {
      const { data } = await apiClient.post('/admin/fleet-types/', form)
      categories.value.push(data)
    }
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    formError.value = typeof detail === 'object'
      ? Object.values(detail).flat().join(' ')
      : 'Could not save this fleet type. Please try again.'
  } finally {
    saving.value = false
  }
}

async function toggleActive(category) {
  busyId.value = category.id
  try {
    const { data } = await apiClient.patch(`/admin/fleet-types/${category.id}/`, { is_active: !category.is_active })
    Object.assign(category, data)
  } catch {
    error.value = 'Could not update this fleet type.'
  } finally {
    busyId.value = null
  }
}

async function deleteCategory(category) {
  if (!confirm(`Delete "${category.name}"? This cannot be undone.`)) return
  busyId.value = category.id
  try {
    await apiClient.delete(`/admin/fleet-types/${category.id}/`)
    categories.value = categories.value.filter((c) => c.id !== category.id)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Could not delete this fleet type.'
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
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="font-[Georgia] text-2xl font-bold text-white">Manage Fleet Types</h1>
        <p class="mt-1 text-sm text-slate-400">
          The vehicle categories shown across the site (e.g. "Executive SUV") - add new ones here instead of
          editing code. Deactivate a type to stop offering it for new vehicles/applications without deleting
          it or affecting vehicles that already use it.
        </p>
      </div>
      <button
        v-if="auth.user?.is_superuser"
        class="flex items-center gap-2 rounded-lg bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400"
        @click="openAddModal"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        Add Fleet Type
      </button>
    </div>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <div v-if="!loading" class="mt-6 overflow-x-auto rounded-xl border border-navy-800">
      <table class="w-full text-left text-sm">
        <thead class="bg-navy-900 text-slate-400">
          <tr>
            <th class="px-4 py-3">Name</th>
            <th class="px-4 py-3">Slug</th>
            <th class="px-4 py-3">Order</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-navy-800 bg-navy-950">
          <tr v-for="category in categories" :key="category.id">
            <td class="px-4 py-3 font-medium text-white">{{ category.name }}</td>
            <td class="px-4 py-3 text-slate-400">{{ category.slug }}</td>
            <td class="px-4 py-3 text-slate-300">{{ category.order }}</td>
            <td class="px-4 py-3">
              <span :class="category.is_active ? 'text-gold-400' : 'text-slate-500'">
                {{ category.is_active ? 'Active' : 'Inactive' }}
              </span>
            </td>
            <td class="space-x-2 whitespace-nowrap px-4 py-3">
              <button
                v-if="auth.user?.is_superuser"
                :disabled="busyId === category.id"
                class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="openEditModal(category)"
              >
                Edit
              </button>
              <button
                v-if="auth.user?.is_superuser"
                :disabled="busyId === category.id"
                class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
                @click="toggleActive(category)"
              >
                {{ category.is_active ? 'Deactivate' : 'Activate' }}
              </button>
              <button
                v-if="auth.user?.is_superuser"
                :disabled="busyId === category.id"
                class="rounded-md border border-red-400 px-2 py-1 text-xs font-semibold text-red-400 hover:bg-red-400 hover:text-navy-950 disabled:opacity-50"
                @click="deleteCategory(category)"
              >
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!categories.length" class="p-6 text-center text-slate-400">No fleet types yet.</p>
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
          <div class="w-full max-w-md rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">{{ modalTitle() }}</h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ formError }}</p>

            <form class="space-y-4" @submit.prevent="saveCategory">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Name *</label>
                <input
                  v-model="form.name" type="text" placeholder="e.g. Luxury Convertible" required
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Display Order</label>
                <input
                  v-model="form.order" type="number" min="0"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                />
                <p class="mt-1 text-xs text-slate-500">Lower numbers show first in filters and dropdowns.</p>
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
