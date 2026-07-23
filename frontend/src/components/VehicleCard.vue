<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import apiClient from '../api/client'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  vehicle: {
    type: Object,
    required: true,
  },
})
const emit = defineEmits(['unfavorited'])

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const isFavorited = ref(props.vehicle.is_favorited)
const togglingFavorite = ref(false)

// Vue reuses this component instance across re-renders of the same v-for key, so a fresh
// vehicle prop (e.g. after the parent refetches) wouldn't otherwise update local state.
watch(
  () => props.vehicle.is_favorited,
  (value) => {
    isFavorited.value = value
  },
)

async function toggleFavorite(event) {
  event.preventDefault()
  event.stopPropagation()
  if (!auth.isAuthenticated) {
    router.push({ name: 'login', query: { redirect: route.fullPath } })
    return
  }
  if (togglingFavorite.value) return
  togglingFavorite.value = true
  const wasFavorited = isFavorited.value
  isFavorited.value = !wasFavorited // optimistic
  try {
    const { data } = await apiClient.post(`/vehicles/${props.vehicle.id}/toggle_favorite/`)
    isFavorited.value = data.is_favorited
    if (wasFavorited && !data.is_favorited) emit('unfavorited', props.vehicle.id)
  } catch {
    isFavorited.value = wasFavorited // revert on failure
  } finally {
    togglingFavorite.value = false
  }
}
</script>

<template>
  <RouterLink
    :to="`/fleet/${vehicle.id}`"
    class="group flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg shadow-slate-200/60 transition-all duration-300 ease-out hover:-translate-y-1 hover:border-gold-300 hover:shadow-xl hover:shadow-gold-500/10"
  >
    <div class="relative aspect-[4/3] w-full overflow-hidden bg-slate-100">
      <img
        v-if="vehicle.image"
        :src="vehicle.image"
        :alt="vehicle.name"
        class="h-full w-full object-cover transition-transform duration-500 ease-out group-hover:scale-110"
      />
      <div v-else class="flex h-full items-center justify-center text-slate-400">No photo yet</div>

      <!-- Real social proof - a genuine completed-trip count, never a fabricated "X viewing now". -->
      <span
        v-if="vehicle.trips_completed > 0"
        class="absolute right-3 top-3 rounded-full bg-navy-950/80 px-2.5 py-1 text-xs font-semibold text-gold-400 backdrop-blur"
      >
        {{ vehicle.trips_completed }} trip{{ vehicle.trips_completed === 1 ? '' : 's' }} completed
      </span>

      <button
        type="button"
        class="absolute left-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-navy-950/60 text-white backdrop-blur transition hover:bg-navy-950/80 disabled:cursor-not-allowed"
        :aria-label="isFavorited ? 'Remove from favorites' : 'Add to favorites'"
        :disabled="togglingFavorite"
        @click="toggleFavorite"
      >
        <svg v-if="isFavorited" class="h-4 w-4 text-red-400" fill="currentColor" viewBox="0 0 24 24">
          <path
            d="M12 21s-6.716-4.35-9.428-8.028C.86 10.42 1.02 7.36 3.343 5.6a5.5 5.5 0 0 1 7.657 1.02L12 7.8l1-1.18a5.5 5.5 0 0 1 7.657-1.02c2.323 1.76 2.483 4.82.77 7.372C18.716 16.65 12 21 12 21Z"
          />
        </svg>
        <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M12 21s-6.716-4.35-9.428-8.028C.86 10.42 1.02 7.36 3.343 5.6a5.5 5.5 0 0 1 7.657 1.02L12 7.8l1-1.18a5.5 5.5 0 0 1 7.657-1.02c2.323 1.76 2.483 4.82.77 7.372C18.716 16.65 12 21 12 21Z"
          />
        </svg>
      </button>
    </div>

    <div class="flex flex-1 flex-col gap-2 p-4">
      <h3 class="font-[Georgia] text-lg font-bold uppercase tracking-wide text-navy-900">
        {{ vehicle.name }}
      </h3>
      <p class="text-sm font-semibold text-brand-blue-600">
        {{ vehicle.category_name || vehicle.category }}
      </p>
      <p class="flex items-center gap-1 text-sm text-slate-600">{{ vehicle.passenger_capacity }} Passengers</p>
      <p v-if="vehicle.tagline" class="text-sm text-slate-500">{{ vehicle.tagline }}</p>

      <div class="mt-auto flex items-center justify-between pt-3">
        <span class="text-lg font-bold text-navy-900">
          KES {{ Number(vehicle.price_per_day).toLocaleString()
          }}<span class="text-sm font-normal text-slate-500">/day</span>
        </span>
        <span
          class="flex items-center gap-1 rounded-md bg-gold-500 px-3 py-1.5 text-sm font-semibold text-navy-950 transition-colors group-hover:bg-gold-400"
        >
          View Details
          <svg
            class="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-0.5"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </span>
      </div>
    </div>
  </RouterLink>
</template>
