<script setup>
import logoIcon from '../assets/logo-icon.png'

defineProps({
  size: {
    type: Number,
    default: 40,
  },
})
</script>

<template>
  <img
    :src="logoIcon"
    alt="SilverLake Car Rentals"
    :style="{ width: `${size}px`, height: `${size}px` }"
    class="shrink-0 rounded-full object-cover"
  />
</template>
