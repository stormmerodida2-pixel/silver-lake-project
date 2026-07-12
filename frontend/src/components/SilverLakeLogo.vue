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
    :style="{ height: `${size}px`, width: 'auto' }"
    class="shrink-0 object-contain"
  />
</template>
