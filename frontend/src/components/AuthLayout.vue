<script setup>
// Reuses the Home hero's gradient/glow treatment and tagline rather than a live vehicle photo -
// a real photo panel would be empty on any deployment with patchy fleet-photo coverage (see
// VehiclePhotoPlaceholder.vue), which is exactly the "feels unfinished" problem this is meant
// to fix, not repeat.
const trustPoints = [
  { text: 'Local expertise, rooted in Kisumu', icon: 'pin' },
  { text: 'National reach, across Kenya', icon: 'route' },
  { text: 'A personal touch, every trip', icon: 'heart' },
]
</script>

<template>
  <div class="flex flex-col bg-page lg:min-h-screen lg:flex-row">
    <!-- Brand panel - desktop only; mobile gets the compact logo lockup below instead. -->
    <div
      class="relative hidden w-[42%] shrink-0 overflow-hidden border-r border-border-subtle bg-linear-to-b from-surface to-page lg:flex lg:flex-col lg:justify-center"
    >
      <div class="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-accent-bg/10 blur-3xl"></div>
      <div
        class="pointer-events-none absolute -left-24 bottom-10 h-72 w-72 rounded-full bg-brand-blue-500/10 blur-3xl"
      ></div>

      <div class="relative px-12">
        <h1 class="max-w-sm font-[Georgia] text-3xl font-bold leading-tight text-foreground">
          We don't just move you, <span class="text-accent">we elevate your journey.</span>
        </h1>
      </div>

      <ul class="relative mt-12 flex flex-col gap-5 px-12 text-sm text-foreground-secondary">
        <li v-for="point in trustPoints" :key="point.text" class="flex items-center gap-3">
          <span
            class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-accent-border/40 bg-page text-accent"
          >
            <svg
              v-if="point.icon === 'pin'"
              class="h-4 w-4"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M12 21s6-5.2 6-10.5A6 6 0 0 0 6 10.5C6 15.8 12 21 12 21Z"
              />
              <circle cx="12" cy="10.5" r="2.2" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <svg
              v-else-if="point.icon === 'route'"
              class="h-4 w-4"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" d="M3 17l4-7 3 4 3-6 5 9" />
              <path stroke-linecap="round" stroke-linejoin="round" d="M3 20h18" />
            </svg>
            <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
              <path
                d="M12 21s-6.716-4.35-9.428-8.028C.86 10.42 1.02 7.36 3.343 5.6a5.5 5.5 0 0 1 7.657 1.02L12 7.8l1-1.18a5.5 5.5 0 0 1 7.657-1.02c2.323 1.76 2.483 4.82.77 7.372C18.716 16.65 12 21 12 21Z"
              />
            </svg>
          </span>
          {{ point.text }}
        </li>
      </ul>
    </div>

    <!-- Form panel -->
    <div class="flex flex-1 flex-col px-4 py-12 sm:px-6 lg:justify-center lg:px-16">
      <div class="mx-auto w-full max-w-md">
        <slot />
      </div>
    </div>
  </div>
</template>
