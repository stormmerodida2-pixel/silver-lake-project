<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import apiClient from '../api/client'

const props = defineProps({
  vehicleId: { type: [Number, String], required: true },
})

const WEEKDAY_LABELS = ['S', 'M', 'T', 'W', 'T', 'F', 'S']

const loading = ref(true)
const error = ref('')
const bookedRanges = ref([]) // [{ start_date: 'YYYY-MM-DD', end_date: 'YYYY-MM-DD' }, ...]

const today = new Date()
today.setHours(0, 0, 0, 0)
const viewYear = ref(today.getFullYear())
const viewMonth = ref(today.getMonth()) // 0-11

const monthLabel = computed(() =>
  new Date(viewYear.value, viewMonth.value, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' }),
)

// The calendar never lets you navigate before the current month - past availability isn't
// useful, and it keeps "Previous" simple to disable rather than clamping mid-navigation.
const isCurrentMonth = computed(() => viewYear.value === today.getFullYear() && viewMonth.value === today.getMonth())

function isBooked(date) {
  return bookedRanges.value.some((range) => date >= range.start_date && date <= range.end_date)
}

function toDateString(year, month, day) {
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

const calendarDays = computed(() => {
  const firstWeekday = new Date(viewYear.value, viewMonth.value, 1).getDay()
  const daysInMonth = new Date(viewYear.value, viewMonth.value + 1, 0).getDate()
  const days = []

  for (let i = 0; i < firstWeekday; i++) days.push(null)
  for (let day = 1; day <= daysInMonth; day++) {
    const dateString = toDateString(viewYear.value, viewMonth.value, day)
    days.push({
      day,
      dateString,
      isPast: dateString < toDateString(today.getFullYear(), today.getMonth(), today.getDate()),
      isBooked: isBooked(dateString),
    })
  }
  return days
})

function prevMonth() {
  if (isCurrentMonth.value) return
  if (viewMonth.value === 0) {
    viewMonth.value = 11
    viewYear.value -= 1
  } else {
    viewMonth.value -= 1
  }
}

function nextMonth() {
  if (viewMonth.value === 11) {
    viewMonth.value = 0
    viewYear.value += 1
  } else {
    viewMonth.value += 1
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await apiClient.get(`/vehicles/${props.vehicleId}/availability/`)
    bookedRanges.value = data
  } catch {
    error.value = "Could not load this vehicle's availability."
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.vehicleId, load)
</script>

<template>
  <div class="rounded-xl border border-slate-200 bg-white p-4">
    <div class="flex items-center justify-between">
      <button
        type="button"
        class="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-navy-900 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
        :disabled="isCurrentMonth"
        aria-label="Previous month"
        @click="prevMonth"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
      </button>
      <p class="text-sm font-semibold text-navy-900">{{ monthLabel }}</p>
      <button
        type="button"
        class="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-navy-900"
        aria-label="Next month"
        @click="nextMonth"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </button>
    </div>

    <p v-if="error" class="mt-3 text-xs text-red-600">{{ error }}</p>

    <template v-else>
      <div class="mt-3 grid grid-cols-7 gap-1 text-center text-[11px] font-semibold uppercase text-slate-400">
        <span v-for="(label, i) in WEEKDAY_LABELS" :key="i">{{ label }}</span>
      </div>
      <div class="mt-1 grid grid-cols-7 gap-1">
        <div
          v-for="(cell, i) in calendarDays"
          :key="i"
          class="flex aspect-square items-center justify-center rounded-md text-xs"
          :class="{
            'text-slate-200': cell?.isPast,
            'bg-red-50 text-red-400 line-through': cell && !cell.isPast && cell.isBooked,
            'text-slate-700': cell && !cell.isPast && !cell.isBooked,
          }"
        >
          {{ cell?.day ?? '' }}
        </div>
      </div>

      <div class="mt-3 flex items-center gap-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
        <span class="flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-full bg-red-100" /> Booked</span>
        <span class="flex items-center gap-1.5"
          ><span class="h-2.5 w-2.5 rounded-full border border-slate-300" /> Available</span
        >
      </div>
    </template>
  </div>
</template>
