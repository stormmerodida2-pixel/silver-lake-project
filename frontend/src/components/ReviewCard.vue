<script setup>
defineProps({
  review: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <div class="rounded-xl border border-border-subtle bg-surface p-5 shadow-lg shadow-black/20">
    <p class="text-accent-strong">
      <span v-for="n in 5" :key="n">{{ n <= review.rating ? '★' : '☆' }}</span>
    </p>
    <p class="mt-2 text-sm text-foreground-secondary">&ldquo;{{ review.comment }}&rdquo;</p>
    <img
      v-if="review.photo"
      :src="review.photo"
      :alt="`Photo from ${review.customer_name}'s trip`"
      class="mt-3 h-32 w-full rounded-lg object-cover"
    />
    <p class="mt-3 text-sm font-semibold text-foreground">- {{ review.customer_name }}</p>
  </div>
</template>
