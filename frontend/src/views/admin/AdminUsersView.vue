<script setup>
import { onMounted, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'

const { items: users, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/users/')
const busyId = ref(null)

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
    <h1 class="font-[Georgia] text-2xl font-bold text-white">Manage Users</h1>

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
  </div>
</template>
