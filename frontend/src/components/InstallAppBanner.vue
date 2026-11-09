<script setup>
import { computed, ref } from 'vue'

import { installState, isIos, promptInstall, rememberDismissal, wasRecentlyDismissed } from '../utils/pwaInstall'

// Sits in the page flow under the nav (not fixed to the bottom) so it can never cover
// StickyMobileCTA's Book Now bar on a phone.
const dismissed = ref(wasRecentlyDismissed())
const onIos = isIos()

const visible = computed(
  () => !window.__PRERENDERING__ && !dismissed.value && !installState.installed && (installState.canPrompt || onIos),
)

function dismiss() {
  dismissed.value = true
  rememberDismissal()
}

async function install() {
  const outcome = await promptInstall()
  // Said "no" to the browser's own dialog - treat it like closing the banner, don't nag.
  if (outcome === 'dismissed') dismiss()
}
</script>

<template>
  <div v-if="visible" class="mx-auto w-full max-w-6xl px-4 pt-4 sm:px-6">
    <div
      class="flex items-center gap-3 rounded-xl border-l-4 border-accent-border-strong bg-surface p-4 shadow-lg shadow-black/20"
      role="region"
      aria-label="Install the SilverLake app"
    >
      <img src="/icons/icon-192.png" alt="" class="h-11 w-11 shrink-0 rounded-xl" />
      <div class="min-w-0 flex-1">
        <p class="font-semibold text-foreground">Get the SilverLake app</p>
        <p v-if="installState.canPrompt" class="mt-0.5 text-sm text-foreground-muted">
          Book and track your rides faster, right from your home screen.
        </p>
        <p v-else class="mt-0.5 text-sm text-foreground-muted">
          Tap
          <svg
            class="inline h-4 w-4 align-text-bottom text-accent"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
            aria-label="Share"
            role="img"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M12 3v12m0-12L8 7m4-4l4 4M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7"
            />
          </svg>
          <strong class="text-foreground">Share</strong>, then
          <strong class="text-foreground">Add to Home Screen</strong>.
        </p>
      </div>
      <button
        v-if="installState.canPrompt"
        class="shrink-0 rounded-lg bg-accent-bg px-4 py-2 text-sm font-semibold text-on-accent transition hover:bg-accent-bg-hover"
        @click="install"
      >
        Install
      </button>
      <button
        class="shrink-0 text-foreground-subtle transition-colors hover:text-foreground"
        aria-label="Dismiss"
        @click="dismiss"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  </div>
</template>
