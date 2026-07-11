<script setup>
import { onMounted } from 'vue'

import { useCatalogStore } from '../stores/catalog'
import ReviewCard from '../components/ReviewCard.vue'

const catalog = useCatalogStore()

onMounted(() => {
  catalog.fetchReviews()
})
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <h1 class="text-center font-[Georgia] text-3xl font-bold text-navy-900">Customer Reviews</h1>
      <p class="mt-2 text-center text-sm text-slate-500">
        Shared by customers after their trip - book with us and yours could be next.
      </p>

      <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <ReviewCard v-for="review in catalog.reviews" :key="review.id" :review="review" />
      </div>
      <p v-if="!catalog.reviews.length" class="mt-10 text-center text-slate-500">No reviews yet.</p>
    </div>
  </div>
</template>
