<script setup>
import { onMounted, reactive, ref } from 'vue'

import apiClient from '../api/client'
import { useCatalogStore } from '../stores/catalog'
import ReviewCard from '../components/ReviewCard.vue'

const catalog = useCatalogStore()

const form = reactive({
  customer_name: '',
  rating: 5,
  comment: '',
})
const submitting = ref(false)
const submitted = ref(false)
const error = ref('')

onMounted(() => {
  catalog.fetchReviews()
})

async function submitReview() {
  submitting.value = true
  error.value = ''
  try {
    await apiClient.post('/reviews/', form)
    submitted.value = true
    form.customer_name = ''
    form.rating = 5
    form.comment = ''
  } catch (err) {
    error.value = 'Could not submit your review. Please try again.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
    <h1 class="text-center font-[Georgia] text-3xl font-bold text-white">Customer Reviews</h1>

    <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
      <ReviewCard v-for="review in catalog.reviews" :key="review.id" :review="review" />
    </div>
    <p v-if="!catalog.reviews.length" class="mt-10 text-center text-slate-400">No reviews yet - be the first!</p>

    <div class="mx-auto mt-16 max-w-lg rounded-xl border border-navy-800 bg-navy-900 p-6">
      <h2 class="font-[Georgia] text-xl font-bold text-white">Share your experience</h2>

      <p v-if="submitted" class="mt-4 text-sm text-gold-400">
        Thanks! Your review has been submitted and will appear once approved.
      </p>

      <form v-else class="mt-4 space-y-4" @submit.prevent="submitReview">
        <div>
          <label class="mb-1 block text-sm text-slate-300">Your name</label>
          <input
            v-model="form.customer_name"
            type="text"
            required
            class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm text-slate-300">Rating</label>
          <select
            v-model.number="form.rating"
            class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
          >
            <option v-for="n in 5" :key="n" :value="n">{{ n }} Star{{ n > 1 ? 's' : '' }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-sm text-slate-300">Comment</label>
          <textarea
            v-model="form.comment"
            required
            rows="4"
            class="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-white focus:border-gold-400 focus:outline-none"
          ></textarea>
        </div>
        <p v-if="error" class="text-sm text-red-400">{{ error }}</p>
        <button
          type="submit"
          :disabled="submitting"
          class="w-full rounded-md bg-gold-500 px-4 py-2 font-semibold text-navy-950 transition hover:bg-gold-400 disabled:opacity-60"
        >
          {{ submitting ? 'Submitting...' : 'Submit Review' }}
        </button>
      </form>
    </div>
  </div>
</template>
