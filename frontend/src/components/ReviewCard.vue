<script setup>
defineProps({
  review: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-lg shadow-slate-200/60">
    <p class="text-gold-500">
      <span v-for="n in 5" :key="n">{{ n <= review.rating ? '★' : '☆' }}</span>
    </p>
    <p class="mt-2 text-sm text-slate-700">&ldquo;{{ review.comment }}&rdquo;</p>
    <p class="mt-3 text-sm font-semibold text-navy-900">- {{ review.customer_name }}</p>
    <p v-if="review.driver_name" class="text-xs text-slate-500">Trip with {{ review.driver_name }}</p>
  </div>
</template>
