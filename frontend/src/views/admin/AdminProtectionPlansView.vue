<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { confirmDialog } from '../../utils/dialogs'

const { items: plans, loading, error, load } = useAdminList('/admin/protection-plans/')
const busyId = ref(null)

const showModal = ref(false)
const editingId = ref(null)
const saving = ref(false)
const formError = ref('')
const form = reactive({
  name: '',
  price_per_day: '',
  excess_reduction_description: '',
  is_active: true,
  order: 0,
})

function openAddModal() {
  editingId.value = null
  Object.assign(form, {
    name: '',
    price_per_day: '',
    excess_reduction_description: '',
    is_active: true,
    order: 0,
  })
  formError.value = ''
  showModal.value = true
}

function openEditModal(plan) {
  editingId.value = plan.id
  Object.assign(form, {
    name: plan.name,
    price_per_day: plan.price_per_day,
    excess_reduction_description: plan.excess_reduction_description,
    is_active: plan.is_active,
    order: plan.order,
  })
  formError.value = ''
  showModal.value = true
}

async function savePlan() {
  formError.value = ''
  saving.value = true
  const payload = {
    name: form.name.trim(),
    price_per_day: form.price_per_day,
    excess_reduction_description: form.excess_reduction_description.trim(),
    is_active: form.is_active,
    order: form.order,
  }
  try {
    if (editingId.value) {
      const { data } = await apiClient.patch(`/admin/protection-plans/${editingId.value}/`, payload)
      const index = plans.value.findIndex((p) => p.id === editingId.value)
      plans.value[index] = data
    } else {
      const { data } = await apiClient.post('/admin/protection-plans/', payload)
      plans.value.push(data)
      plans.value.sort((a, b) => a.order - b.order || a.price_per_day - b.price_per_day)
    }
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    formError.value = typeof detail === 'object' ? Object.values(detail).flat().join(' ') : 'Could not save this plan.'
  } finally {
    saving.value = false
  }
}

async function deletePlan(plan) {
  if (!(await confirmDialog(`Delete the "${plan.name}" protection plan? This cannot be undone.`, { danger: true })))
    return
  busyId.value = plan.id
  try {
    await apiClient.delete(`/admin/protection-plans/${plan.id}/`)
    plans.value = plans.value.filter((p) => p.id !== plan.id)
  } catch {
    error.value = 'Could not delete this plan.'
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
        <h1 class="font-[Georgia] text-2xl font-bold text-white">Protection Plans</h1>
        <p class="mt-1 text-sm text-slate-400">
          Optional damage-waiver tiers a customer can add to a self-drive booking, priced per rental day. Only active
          plans are offered at checkout.
        </p>
      </div>
      <button
        class="flex shrink-0 items-center gap-2 rounded-lg bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400"
        @click="openAddModal"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        Add Plan
      </button>
    </div>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <div v-if="!loading" class="mt-6 space-y-3">
      <div v-for="plan in plans" :key="plan.id" class="rounded-xl border border-navy-800 bg-navy-900 p-4">
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gold-500/10 text-gold-400">
              <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M12 2.25c-3.75 3-8.25 3.75-8.25 3.75v6.75c0 5.25 3.75 8.25 8.25 9.75 4.5-1.5 8.25-4.5 8.25-9.75V6c0 0-4.5-.75-8.25-3.75Z"
                />
              </svg>
            </span>
            <div>
              <p class="flex items-center gap-2 font-semibold text-white">
                {{ plan.name }}
                <span
                  v-if="!plan.is_active"
                  class="rounded-full bg-slate-700 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-300"
                >
                  Inactive
                </span>
              </p>
              <p class="text-xs text-slate-500">
                KES {{ Number(plan.price_per_day).toLocaleString() }}/day
                <template v-if="plan.excess_reduction_description"> &middot; {{ plan.excess_reduction_description }}</template>
              </p>
            </div>
          </div>
          <div class="flex shrink-0 gap-2">
            <button
              :disabled="busyId === plan.id"
              class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
              @click="openEditModal(plan)"
            >
              Edit
            </button>
            <button
              :disabled="busyId === plan.id"
              class="rounded-md border border-red-400 px-2 py-1 text-xs font-semibold text-red-400 hover:bg-red-400 hover:text-navy-950 disabled:opacity-50"
              @click="deletePlan(plan)"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
      <p v-if="!plans.length" class="p-6 text-center text-slate-400">No protection plans yet.</p>
    </div>

    <!-- Add/Edit Plan Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-lg rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">{{ editingId ? 'Edit Plan' : 'Add Plan' }}</h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ formError }}</p>

            <form class="space-y-4" @submit.prevent="savePlan">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Plan Name *</label>
                <input
                  v-model="form.name"
                  type="text"
                  required
                  placeholder="e.g. Standard"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                    >Price/Day (KES) *</label
                  >
                  <input
                    v-model="form.price_per_day"
                    type="number"
                    min="0.01"
                    step="0.01"
                    required
                    placeholder="e.g. 1000"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Order</label>
                  <input
                    v-model="form.order"
                    type="number"
                    min="0"
                    step="1"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                </div>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                  >Excess Reduction Description</label
                >
                <input
                  v-model="form.excess_reduction_description"
                  type="text"
                  placeholder="e.g. Reduces your excess to KES 20,000"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                />
              </div>
              <label class="flex items-center gap-2 text-sm text-slate-300">
                <input v-model="form.is_active" type="checkbox" class="rounded border-navy-700 bg-navy-800" />
                Active (offered at checkout)
              </label>

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
                  {{ saving ? 'Saving…' : 'Save Plan' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
