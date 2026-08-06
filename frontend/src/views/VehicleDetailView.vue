<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import apiClient from '../api/client'
import AvailabilityCalendar from '../components/AvailabilityCalendar.vue'
import { useCatalogStore } from '../stores/catalog'
import { trackEvent } from '../utils/analytics'
import { setPageMeta, setStructuredData } from '../utils/seo'

const route = useRoute()
const router = useRouter()
const catalog = useCatalogStore()

const vehicle = ref(null)
const loading = ref(true)
const error = ref('')

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

const selfDriveUrl = computed(() => `/book?vehicle=${vehicle.value?.id}&service=self_drive`)
const withDriverUrl = computed(() => `/book?vehicle=${vehicle.value?.id}&service=with_driver`)
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
            <div class="rounded-2xl border border-border-subtle bg-surface p-6 shadow-lg lg:sticky lg:top-6">
              <p class="text-center text-2xl font-bold text-foreground">
                KES {{ Number(vehicle.price_per_day).toLocaleString() }}
                <span class="text-sm font-normal text-foreground-muted">/day</span>
              </p>
              <p class="mt-1 text-center text-xs text-foreground-subtle">30% deposit required to confirm</p>

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
    </template>
  </div>
</template>
