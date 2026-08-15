<script setup>
defineProps({
  size: {
    type: String,
    default: 'md', // 'sm' | 'md' | 'lg'
    validator: (v) => ['sm', 'md', 'lg'].includes(v),
  },
})

const ICON_SIZES = { sm: 'h-7 w-7', md: 'h-10 w-10', lg: 'h-14 w-14' }
</script>

<template>
  <div class="flex h-full flex-col items-center justify-center gap-2 text-foreground-subtle">
    <svg
      :class="ICON_SIZES[size]"
      class="opacity-50"
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        d="M3 13l1.4-4.2A2 2 0 0 1 6.3 7.4h11.4a2 2 0 0 1 1.9 1.4L21 13"
      />
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        d="M3 13v3.5A1.5 1.5 0 0 0 4.5 18H6a1.5 1.5 0 0 0 1.5-1.5V16h9v.5A1.5 1.5 0 0 0 18 18h1.5a1.5 1.5 0 0 0 1.5-1.5V13"
      />
      <path stroke-linecap="round" stroke-linejoin="round" d="M3 13h18" />
      <circle cx="7.5" cy="16" r="1.4" />
      <circle cx="16.5" cy="16" r="1.4" />
    </svg>
    <span class="text-xs font-medium uppercase tracking-wide"><slot>No photo yet</slot></span>
  </div>
</template>
