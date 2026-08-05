<script setup>
import { useThemeStore } from '../stores/theme'

const theme = useThemeStore()
</script>

<template>
  <button
    type="button"
    class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-foreground-muted transition hover:bg-surface-2 hover:text-accent"
    :aria-label="theme.theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
    @click="theme.toggleTheme()"
  >
    <svg
      v-if="theme.theme === 'dark'"
      xmlns="http://www.w3.org/2000/svg"
      class="h-5 w-5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      stroke-width="1.8"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        d="M12 3v1.5M12 19.5V21M4.22 4.22l1.06 1.06M18.72 18.72l1.06 1.06M3 12h1.5M19.5 12H21M4.22 19.78l1.06-1.06M18.72 5.28l1.06-1.06M16.5 12a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0Z"
      />
    </svg>
    <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
      <path stroke-linecap="round" stroke-linejoin="round" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79Z" />
    </svg>
  </button>
</template>
