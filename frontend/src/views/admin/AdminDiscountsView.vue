<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../../api/client'
import { useAdminList } from '../../composables/useAdminList'
import { confirmDialog } from '../../utils/dialogs'

const { items: codes, loading, error, load } = useAdminList('/admin/discounts/')
const busyId = ref(null)

function describeDiscount(code) {
  return code.discount_type === 'percent'
    ? `${Number(code.value)}% off`
    : `KES ${Number(code.value).toLocaleString()} off`
}

const showModal = ref(false)
const saving = ref(false)
const formError = ref('')
const form = reactive({
  code: '',
  discount_type: 'fixed',
  value: '',
})

function openAddModal() {
  Object.assign(form, { code: '', discount_type: 'fixed', value: '' })
  formError.value = ''
  showModal.value = true
}

async function saveCode() {
  formError.value = ''
  if (!form.value || Number(form.value) <= 0) {
    formError.value = 'Enter a value greater than zero.'
    return
  }
  saving.value = true
  try {
    const { data } = await apiClient.post('/admin/discounts/', {
      code: form.code.trim(),
      discount_type: form.discount_type,
      value: form.value,
    })
    codes.value.unshift(data)
    showModal.value = false
  } catch (err) {
    const detail = err?.response?.data
    formError.value =
      typeof detail === 'object' ? Object.values(detail).flat().join(' ') : 'Could not create this discount code.'
  } finally {
    saving.value = false
  }
}

async function toggleActive(code) {
  busyId.value = code.id
  try {
    const { data } = await apiClient.patch(`/admin/discounts/${code.id}/`, { is_active: !code.is_active })
    Object.assign(code, data)
  } catch {
    error.value = 'Could not update this discount code.'
  } finally {
    busyId.value = null
  }
}

async function deleteCode(code) {
  if (!(await confirmDialog(`Delete code "${code.code}"? This cannot be undone.`, { danger: true }))) return
  busyId.value = code.id
  try {
    await apiClient.delete(`/admin/discounts/${code.id}/`)
    codes.value = codes.value.filter((c) => c.id !== code.id)
  } catch {
    error.value = 'Could not delete this discount code.'
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
        <h1 class="font-[Georgia] text-2xl font-bold text-white">Discount Codes</h1>
        <p class="mt-1 text-sm text-slate-400">
          Generate single-use codes a customer can enter at booking time to reduce their total. Each code works once,
          for anyone - the first booking to use it burns it for good.
        </p>
      </div>
      <button
        class="flex items-center gap-2 rounded-lg bg-gold-500 px-4 py-2 text-sm font-semibold text-navy-950 transition-colors hover:bg-gold-400"
        @click="openAddModal"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        Generate Code
      </button>
    </div>

    <p v-if="loading" class="mt-10 text-center text-slate-400">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-red-400">{{ error }}</p>

    <div v-if="!loading" class="mt-6 space-y-3">
      <div
        v-for="code in codes"
        :key="code.id"
        class="rounded-xl border p-4"
        :class="code.is_active ? 'border-navy-800 bg-navy-900' : 'border-navy-800 bg-navy-950 opacity-60'"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <p class="font-mono text-base font-bold tracking-wide text-white">{{ code.code }}</p>
              <span
                class="rounded-full bg-navy-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gold-400"
              >
                {{ describeDiscount(code) }}
              </span>
              <span
                v-if="code.is_redeemed"
                class="rounded-full bg-slate-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400"
              >
                Used{{ code.redeemed_booking_id ? ` - Booking #${code.redeemed_booking_id}` : '' }}
              </span>
              <span
                v-else
                class="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-400"
              >
                Unused
              </span>
              <span
                v-if="!code.is_active"
                class="rounded-full bg-navy-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500"
              >
                Inactive
              </span>
            </div>
            <p class="mt-2 text-xs text-slate-500">
              Created by {{ code.created_by_name || 'Unknown' }} &middot;
              {{ new Date(code.created_at).toLocaleString() }}
              <template v-if="code.redeemed_at">
                &middot; redeemed {{ new Date(code.redeemed_at).toLocaleString() }}
              </template>
            </p>
          </div>
          <div class="flex shrink-0 gap-2">
            <button
              :disabled="busyId === code.id"
              class="rounded-md border border-navy-700 px-2 py-1 text-xs font-semibold text-slate-300 hover:border-gold-400 hover:text-gold-400 disabled:opacity-50"
              @click="toggleActive(code)"
            >
              {{ code.is_active ? 'Deactivate' : 'Activate' }}
            </button>
            <button
              :disabled="busyId === code.id"
              class="rounded-md border border-red-400 px-2 py-1 text-xs font-semibold text-red-400 hover:bg-red-400 hover:text-navy-950 disabled:opacity-50"
              @click="deleteCode(code)"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
      <p v-if="!codes.length" class="p-6 text-center text-slate-400">No discount codes yet.</p>
    </div>

    <!-- New Discount Code Modal -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="showModal"
          class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-8 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-lg rounded-2xl border border-navy-700 bg-navy-900 p-8 shadow-2xl">
            <div class="mb-6 flex items-center justify-between">
              <h2 class="font-[Georgia] text-xl font-bold text-white">Generate Discount Code</h2>
              <button class="text-slate-400 transition-colors hover:text-white" @click="showModal = false">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <p v-if="formError" class="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{{ formError }}</p>

            <form class="space-y-4" @submit.prevent="saveCode">
              <div>
                <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">Code</label>
                <input
                  v-model="form.code"
                  type="text"
                  placeholder="Leave blank to auto-generate one"
                  class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 font-mono text-sm uppercase text-white placeholder-slate-500 placeholder:normal-case focus:border-gold-500 focus:outline-none"
                />
              </div>
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400"
                    >Discount Type</label
                  >
                  <select
                    v-model="form.discount_type"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white focus:border-gold-500 focus:outline-none"
                  >
                    <option value="fixed">Fixed amount (KES)</option>
                    <option value="percent">Percentage</option>
                  </select>
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">
                    Value {{ form.discount_type === 'percent' ? '(%)' : '(KES)' }} *
                  </label>
                  <input
                    v-model="form.value"
                    type="number"
                    min="0"
                    step="0.01"
                    required
                    :placeholder="form.discount_type === 'percent' ? 'e.g. 10' : 'e.g. 500'"
                    class="w-full rounded-lg border border-navy-700 bg-navy-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-gold-500 focus:outline-none"
                  />
                </div>
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
                  {{ saving ? 'Generating…' : 'Generate Code' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
