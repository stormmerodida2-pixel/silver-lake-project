<script setup>
defineProps({
  size: {
    type: Number,
    default: 40,
  },
})
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M50 8c14 10 26 24 26 40 0 5-1 9-3 13-3-9-11-16-23-16s-20 7-23 16c-2-4-3-8-3-13 0-16 12-30 26-40z"
      fill="#e8cf7d"
      stroke="#c9a227"
      stroke-width="2"
    />
    <path
      d="M50 20c-6 12-6 26 0 38"
      stroke="#0a1730"
      stroke-width="2"
      fill="none"
    />
    <path
      d="M15 66c8-6 22-10 35-10s27 4 35 10"
      stroke="#3b82f6"
      stroke-width="3"
      fill="none"
      stroke-linecap="round"
    />
    <path
      d="M20 76c8-5 20-8 30-8s22 3 30 8"
      stroke="#1d4ed8"
      stroke-width="3"
      fill="none"
      stroke-linecap="round"
      opacity="0.7"
    />
  </svg>
</template>
