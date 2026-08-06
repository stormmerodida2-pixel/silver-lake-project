<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import apiClient from '../api/client'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  vehicle: {
    type: Object,
    required: true,
  },
  startDate: {
    type: String,
    default: '',
  },
  endDate: {
    type: String,
    default: '',
  },
})
const emit = defineEmits(['unfavorited'])

// Carries a date search made on the Fleet listing through to the vehicle's own detail page, so
// its "Book with Driver"/"Self Drive" CTAs can forward the same dates into the booking form
// instead of the customer re-entering them (see VehicleDetailView.vue's own withDriverUrl/
// selfDriveUrl computeds, which read these same query params back out).
const detailHref = computed(() => {
  const query = {}
  if (props.startDate) query.start_date = props.startDate
  if (props.endDate) query.end_date = props.endDate
  return { path: `/fleet/${props.vehicle.id}`, query }
})

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
    :to="detailHref"
    class="group flex flex-col overflow-hidden rounded-3xl border border-border-subtle bg-surface shadow-lg shadow-black/20 transition-all duration-300 ease-out hover:-translate-y-1 hover:border-accent-border/50 hover:shadow-xl hover:shadow-gold-500/10"
  >
    <div class="relative aspect-[4/3] w-full overflow-hidden bg-page">
      <img
        v-if="vehicle.image"
        :src="vehicle.image"
        :alt="vehicle.name"
        class="h-full w-full object-cover transition-transform duration-500 ease-out group-hover:scale-110"
      />
      <div v-else class="flex h-full items-center justify-center text-foreground-subtle">No photo yet</div>

      <!-- Real social proof - a genuine completed-trip count, never a fabricated "X viewing now". -->
      <span
        v-if="vehicle.trips_completed > 0"
        class="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-page/85 px-2.5 py-1 text-xs font-semibold text-accent shadow-lg backdrop-blur"
      >
        &#9733; {{ vehicle.trips_completed }} trip{{ vehicle.trips_completed === 1 ? '' : 's' }}
      </span>

      <button
        type="button"
        class="absolute left-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-page/70 text-foreground backdrop-blur transition hover:bg-page/90 disabled:cursor-not-allowed"
        :aria-label="isFavorited ? 'Remove from favorites' : 'Add to favorites'"
        :disabled="togglingFavorite"
        @click="toggleFavorite"
      >
        <svg v-if="isFavorited" class="h-4 w-4 text-danger" fill="currentColor" viewBox="0 0 24 24">
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

    <div class="flex flex-1 flex-col gap-2 p-5">
      <p class="text-xs font-semibold uppercase tracking-widest text-accent/90">
        {{ vehicle.category_name || vehicle.category }}
      </p>
      <h3 class="font-[Georgia] text-lg font-bold text-foreground">
        {{ vehicle.name }}
      </h3>
      <p class="flex items-center gap-1.5 text-sm text-foreground-muted">
        <svg class="h-4 w-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
          <circle cx="9" cy="7" r="3" stroke-linecap="round" stroke-linejoin="round" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M3.5 18c0-2.8 2.5-5 5.5-5s5.5 2.2 5.5 5" />
          <circle cx="17" cy="8" r="2.4" stroke-linecap="round" stroke-linejoin="round" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M15.2 13.2c2 .3 3.6 1.9 3.8 4" />
        </svg>
        {{ vehicle.passenger_capacity }} Passengers
      </p>
      <p v-if="vehicle.tagline" class="text-sm text-foreground-subtle">{{ vehicle.tagline }}</p>

      <div class="mt-auto flex items-center justify-between pt-4">
        <span class="leading-tight">
          <span class="block text-xs uppercase tracking-wide text-foreground-subtle">From</span>
          <span class="text-lg font-bold text-foreground">
            KES {{ Number(vehicle.price_per_day).toLocaleString() }}<span class="text-sm font-normal text-foreground-muted">/day</span>
          </span>
        </span>
        <span
          class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-accent-bg text-on-accent shadow-lg shadow-gold-500/20 transition-all duration-300 group-hover:bg-accent-bg-hover group-hover:rotate-45"
          aria-hidden="true"
        >
          <svg class="h-4.5 w-4.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7 17L17 7M9 7h8v8" />
          </svg>
        </span>
      </div>
    </div>
  </RouterLink>
</template>
