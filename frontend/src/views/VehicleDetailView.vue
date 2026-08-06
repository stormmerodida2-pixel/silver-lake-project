<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import apiClient from '../api/client'
import AvailabilityCalendar from '../components/AvailabilityCalendar.vue'
import StickyMobileCTA from '../components/StickyMobileCTA.vue'
import { useCatalogStore } from '../stores/catalog'
import { trackEvent } from '../utils/analytics'
import { calculateEstimatedCost, calculateTotalDays, SELF_DRIVE_SURCHARGE_PERCENT } from '../utils/pricing'
import { setPageMeta, setStructuredData } from '../utils/seo'
import { buildWhatsAppLink } from '../utils/whatsapp'

const route = useRoute()
const router = useRouter()
const catalog = useCatalogStore()

const vehicle = ref(null)
const loading = ref(true)
const error = ref('')

// Real, computed social proof - never a fabricated number. Mirrors HomeView.vue's own
// averageRating computed; hidden entirely until there's something genuine to show.
const averageRating = computed(() => {
  if (!catalog.reviews.length) return null
  const total = catalog.reviews.reduce((sum, review) => sum + review.rating, 0)
  return (total / catalog.reviews.length).toFixed(1)
})

// Pre-fills from a date search already run on the Fleet listing (see VehicleCard.vue's
// detailHref) - the customer can still adjust them here before continuing to /book.
const startDate = ref(typeof route.query.start_date === 'string' ? route.query.start_date : '')
const endDate = ref(typeof route.query.end_date === 'string' ? route.query.end_date : '')
const todayString = new Date().toISOString().split('T')[0]

const estimatedDays = computed(() => calculateTotalDays(startDate.value, endDate.value))
// Assumes with-driver pricing (the default/primary service for any vehicle offering both) -
// the self-drive surcharge is called out as a caption instead of adding a second selector here,
// since the exact service type is chosen on the booking form itself.
const estimatedTotal = computed(() =>
  vehicle.value ? calculateEstimatedCost(vehicle.value.price_per_day, estimatedDays.value, 'with_driver') : 0,
)

function trackVehicleView(v) {
  trackEvent('view_item', {
    currency: 'KES',
    value: Number(v.price_per_day),
    items: [{ item_id: String(v.id), item_name: v.name, price: Number(v.price_per_day) }],
  })
}

// Overrides the generic "Vehicle Details" title the router set on navigation - was previously
// missing entirely (unlike BlogPostView.vue's own override), so every vehicle page shipped the
// same generic title regardless of which vehicle. Also adds real Product/Offer structured data
// with this vehicle's actual price - the kind of data an AI answer engine needs to directly
// answer "how much does it cost to rent a Prado in Kisumu."
function applySeo(v) {
  const category = v.category_name || v.category
  const price = Number(v.price_per_day).toLocaleString()
  setPageMeta({
    title: `${v.name} - ${category} for Hire in Kisumu | SilverLake`,
    description: `Hire the ${v.name} in Kisumu from KES ${price}/day, with driver or self-drive. Book online via M-Pesa or bank transfer.`,
    image: v.image,
  })
  setStructuredData('ld-dynamic-vehicle-offer', {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: v.name,
    category,
    image: v.image || undefined,
    offers: {
      '@type': 'Offer',
      price: v.price_per_day,
      priceCurrency: 'KES',
      availability: v.is_available ? 'https://schema.org/InStock' : 'https://schema.org/OutOfStock',
      url: `https://silverlakecarentals.com/fleet/${v.id}`,
    },
  })
}

onMounted(async () => {
  catalog.fetchReviews()
  // Try catalog cache first, fall back to direct API call
  await catalog.fetchVehicles()
  const cached = catalog.vehicles.find((v) => v.id === Number(route.params.id))
  if (cached) {
    vehicle.value = cached
    loading.value = false
    trackVehicleView(cached)
    applySeo(cached)
    return
  }
  try {
    const { data } = await apiClient.get(`/vehicles/${route.params.id}/`)
    vehicle.value = data
    trackVehicleView(data)
    applySeo(data)
  } catch (err) {
    if (err.response?.status === 404) {
      router.replace('/fleet')
    } else {
      error.value = 'Could not load vehicle details.'
    }
  } finally {
    loading.value = false
  }
})

const dateQuery = computed(() =>
  startDate.value && endDate.value ? `&start_date=${startDate.value}&end_date=${endDate.value}` : '',
)
const selfDriveUrl = computed(() => `/book?vehicle=${vehicle.value?.id}&service=self_drive${dateQuery.value}`)
const withDriverUrl = computed(() => `/book?vehicle=${vehicle.value?.id}&service=with_driver${dateQuery.value}`)

const whatsappHref = computed(() =>
  buildWhatsAppLink(`Hello SilverLake Car Rentals, I'm interested in the ${vehicle.value?.name}.`),
)

// Sticky mobile CTA only once the desktop-sticky price card (only sticky at lg: and up) has
// scrolled out of view, so mobile visitors always have a booking affordance reachable without
// scrolling back up.
const priceCardRef = ref(null)
const showStickyCta = ref(false)
let priceCardObserver = null
watch(priceCardRef, (el) => {
  priceCardObserver?.disconnect()
  if (!el) return
  priceCardObserver = new IntersectionObserver(([entry]) => {
    showStickyCta.value = !entry.isIntersecting
  })
  priceCardObserver.observe(el)
})
onBeforeUnmount(() => priceCardObserver?.disconnect())
</script>

<template>
  <div class="bg-page">
    <p v-if="loading" class="py-32 text-center text-foreground-muted">Loading...</p>
    <p v-else-if="error" class="py-32 text-center text-danger">{{ error }}</p>

    <template v-else-if="vehicle">
      <!-- Hero image -->
      <div class="relative h-72 w-full bg-surface sm:h-96">
        <img v-if="vehicle.image" :src="vehicle.image" :alt="vehicle.name" class="h-full w-full object-cover" />
        <div v-else class="flex h-full items-center justify-center text-foreground-subtle text-lg">No photo available</div>
        <div class="pointer-events-none absolute inset-0 bg-gradient-to-t from-navy-950 via-navy-950/10 to-transparent"></div>
        <!-- Back link -->
        <RouterLink
          to="/fleet"
          class="absolute top-4 left-4 flex items-center gap-1.5 rounded-full bg-page/80 px-4 py-2 text-sm font-semibold text-foreground shadow backdrop-blur hover:bg-page"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          All Vehicles
        </RouterLink>
      </div>

      <div class="mx-auto max-w-5xl px-4 py-12 sm:px-6">
        <div class="grid gap-10 lg:grid-cols-3">
          <!-- Left: details -->
          <div class="lg:col-span-2">
            <p class="text-sm font-semibold uppercase tracking-widest text-accent">
              {{ vehicle.category_name || vehicle.category }}
            </p>
            <h1 class="mt-2 font-[Georgia] text-3xl font-bold text-foreground sm:text-4xl">
              {{ vehicle.name }}
            </h1>
            <p v-if="vehicle.tagline" class="mt-2 text-lg text-foreground-muted italic">{{ vehicle.tagline }}</p>

            <!-- Site-wide rating, not fabricated per-vehicle - VehicleCard.vue's own
                 trips_completed badge already covers a genuine per-vehicle popularity signal. -->
            <RouterLink
              v-if="averageRating"
              to="/reviews"
              class="mt-2 inline-flex items-center gap-1.5 text-sm text-foreground-secondary hover:text-accent"
            >
              <span class="font-semibold text-foreground">{{ averageRating }}<span class="text-accent">&#9733;</span></span>
              <span>SilverLake rating &middot; {{ catalog.reviews.length }} reviews</span>
            </RouterLink>

            <!-- Specs grid -->
            <div class="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3">
              <div class="rounded-xl border border-border-subtle bg-surface p-4 text-center">
                <p class="text-2xl font-bold text-foreground">{{ vehicle.passenger_capacity }}</p>
                <p class="mt-1 text-xs font-medium uppercase tracking-wide text-foreground-subtle">Passengers</p>
              </div>
              <div class="rounded-xl border border-border-subtle bg-surface p-4 text-center">
                <p class="text-2xl font-bold text-accent">KES {{ Number(vehicle.price_per_day).toLocaleString() }}</p>
                <p class="mt-1 text-xs font-medium uppercase tracking-wide text-foreground-subtle">Per Day</p>
              </div>
              <div class="rounded-xl border border-border-subtle bg-surface p-4 text-center col-span-2 sm:col-span-1">
                <p class="text-sm font-semibold text-foreground mt-1">
                  <span v-if="vehicle.allow_with_driver && vehicle.allow_self_drive">With Driver &amp; Self Drive</span>
                  <span v-else-if="vehicle.allow_with_driver">With Driver Only</span>
                  <span v-else>Self Drive Only</span>
                </p>
                <p class="mt-1 text-xs font-medium uppercase tracking-wide text-foreground-subtle">Service Type</p>
              </div>
            </div>

            <div v-if="vehicle.description" class="mt-8">
              <h2 class="font-[Georgia] text-xl font-bold text-foreground">About This Vehicle</h2>
              <p class="mt-3 leading-relaxed text-foreground-muted">{{ vehicle.description }}</p>
            </div>

            <!-- Gallery -->
            <div v-if="vehicle.gallery_images?.length" class="mt-8">
              <h2 class="font-[Georgia] text-xl font-bold text-foreground">Gallery</h2>
              <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
                <img
                  v-for="img in vehicle.gallery_images"
                  :key="img.id"
                  :src="img.image"
                  :alt="img.caption || vehicle.name"
                  class="aspect-[4/3] w-full rounded-lg object-cover"
                />
              </div>
            </div>
          </div>

          <!-- Right: booking CTA -->
          <div class="lg:col-span-1">
            <div ref="priceCardRef" class="rounded-2xl border border-border-subtle bg-surface p-6 shadow-lg lg:sticky lg:top-6">
              <p class="text-center text-2xl font-bold text-foreground">
                KES {{ Number(vehicle.price_per_day).toLocaleString() }}
                <span class="text-sm font-normal text-foreground-muted">/day</span>
              </p>
              <p class="mt-1 text-center text-xs text-foreground-subtle">30% deposit required to confirm</p>

              <div class="mt-4 grid grid-cols-2 gap-2">
                <div>
                  <label class="mb-1 block text-xs font-medium text-foreground-muted">Pickup date</label>
                  <input
                    v-model="startDate"
                    type="date"
                    :min="todayString"
                    class="w-full rounded-lg border border-border bg-surface-2 px-2 py-1.5 text-sm text-foreground [color-scheme:dark] focus:border-accent-border focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-medium text-foreground-muted">Return date</label>
                  <input
                    v-model="endDate"
                    type="date"
                    :min="startDate || todayString"
                    class="w-full rounded-lg border border-border bg-surface-2 px-2 py-1.5 text-sm text-foreground [color-scheme:dark] focus:border-accent-border focus:outline-none"
                  />
                </div>
              </div>
              <div v-if="estimatedDays" class="mt-3 rounded-md bg-surface-2 px-3 py-2 text-center text-sm text-foreground-muted">
                {{ estimatedDays }} day{{ estimatedDays > 1 ? 's' : '' }} &middot;
                <span class="font-semibold text-foreground">KES {{ estimatedTotal.toLocaleString() }}</span> estimated
                <span class="block text-xs text-foreground-subtle">Self-drive adds a {{ SELF_DRIVE_SURCHARGE_PERCENT }}% surcharge</span>
              </div>

              <div class="mt-6 space-y-3">
                <RouterLink
                  v-if="vehicle.allow_with_driver"
                  :to="withDriverUrl"
                  class="flex w-full items-center justify-center rounded-xl bg-accent-bg py-3 font-semibold text-on-accent transition hover:bg-accent-bg-hover"
                  @click="
                    trackEvent('select_item', {
                      items: [{ item_id: String(vehicle.id), item_name: vehicle.name }],
                      service_type: 'with_driver',
                    })
                  "
                >
                  Book with Driver
                </RouterLink>
                <RouterLink
                  v-if="vehicle.allow_self_drive"
                  :to="selfDriveUrl"
                  class="flex w-full items-center justify-center rounded-xl border border-border py-3 font-semibold text-foreground transition hover:bg-surface-2"
                  @click="
                    trackEvent('select_item', {
                      items: [{ item_id: String(vehicle.id), item_name: vehicle.name }],
                      service_type: 'self_drive',
                    })
                  "
                >
                  Self Drive
                </RouterLink>
              </div>

              <p class="mt-5 text-center text-xs text-foreground-subtle">
                Need help?
                <a href="tel:+254798184193" class="font-semibold text-accent hover:underline">
                  Call 0798 184 193
                </a>
              </p>
            </div>

            <AvailabilityCalendar :vehicle-id="vehicle.id" class="mt-4" />
          </div>
        </div>
      </div>

      <StickyMobileCTA
        :visible="showStickyCta"
        :book-href="vehicle.allow_with_driver ? withDriverUrl : selfDriveUrl"
        :whatsapp-href="whatsappHref"
      />
    </template>
  </div>
</template>
