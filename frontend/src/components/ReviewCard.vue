<script setup>
defineProps({
  review: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <div class="rounded-xl border border-navy-800 bg-navy-900 p-5 shadow-lg shadow-black/20">
    <p class="text-gold-400">
      <span v-for="n in 5" :key="n">{{ n <= review.rating ? '★' : '☆' }}</span>
    </p>
    <p class="mt-2 text-sm text-slate-200">&ldquo;{{ review.comment }}&rdquo;</p>
    <p class="mt-3 text-sm font-semibold text-white">- {{ review.customer_name }}</p>
  </div>
</template>
