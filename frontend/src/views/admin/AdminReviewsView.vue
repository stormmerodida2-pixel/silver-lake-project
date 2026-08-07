<script setup>
import { computed, onMounted, ref } from 'vue'

import apiClient from '../../api/client'
import { confirmDialog } from '../../utils/dialogs'
import { useAdminList } from '../../composables/useAdminList'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const { items: reviews, nextUrl, loading, loadingMore, error, load, loadMore } = useAdminList('/admin/reviews/')
const busyId = ref(null)
const filter = ref('pending') // 'pending' | 'approved' | 'all'

const filteredReviews = computed(() => {
  if (filter.value === 'all') return reviews.value
  if (filter.value === 'approved') return reviews.value.filter((r) => r.is_approved)
  return reviews.value.filter((r) => !r.is_approved)
})

const starFill = (rating, i) => (i <= rating ? 'text-accent' : 'text-foreground-subtle')

async function approve(review) {
  busyId.value = review.id
  try {
    const { data } = await apiClient.post(`/admin/reviews/${review.id}/approve/`)
    Object.assign(review, data)
  } catch {
    error.value = 'Could not approve this review.'
  } finally {
    busyId.value = null
  }
}

async function reject(review) {
  busyId.value = review.id
  try {
    const { data } = await apiClient.post(`/admin/reviews/${review.id}/reject/`)
    Object.assign(review, data)
  } catch {
    error.value = 'Could not reject this review.'
  } finally {
    busyId.value = null
  }
}

async function deleteReview(review) {
  if (!(await confirmDialog(`Delete review from "${review.customer_name}"? This cannot be undone.`, { danger: true })))
    return
  busyId.value = review.id
  try {
    await apiClient.delete(`/admin/reviews/${review.id}/`)
    reviews.value = reviews.value.filter((r) => r.id !== review.id)
  } catch {
    error.value = 'Could not delete this review.'
  } finally {
    busyId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="font-[Georgia] text-2xl font-bold text-foreground">Review Moderation</h1>

      <!-- Filter tabs -->
      <div class="flex gap-2">
        <button
          v-for="option in ['pending', 'approved', 'all']"
          :key="option"
          class="rounded-md border px-3 py-1.5 text-sm font-medium transition"
          :class="
            filter === option
              ? 'border-accent-border-strong bg-accent-bg text-on-accent'
              : 'border-border text-foreground-secondary hover:border-accent-border hover:text-accent'
          "
          @click="filter = option"
        >
          {{ option.charAt(0).toUpperCase() + option.slice(1) }}
        </button>
      </div>
    </div>

    <p v-if="loading" class="mt-10 text-center text-foreground-muted">Loading...</p>
    <p v-else-if="error" class="mt-4 text-sm text-danger">{{ error }}</p>

    <div v-if="!loading" class="mt-6 space-y-4">
      <!-- Review cards -->
      <div
        v-for="review in filteredReviews"
        :key="review.id"
        class="rounded-xl border bg-surface p-5 transition"
        :class="review.is_approved ? 'border-border-subtle' : 'border-accent-border-strong/40'"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="flex-1">
            <!-- Stars -->
            <div class="flex gap-0.5">
              <svg
                v-for="i in 5"
                :key="i"
                class="h-4 w-4"
                :class="starFill(review.rating, i)"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"
                />
              </svg>
            </div>

            <p class="mt-2 text-sm leading-relaxed text-foreground-secondary">{{ review.comment }}</p>

            <div class="mt-3 flex flex-wrap items-center gap-3 text-xs text-foreground-subtle">
              <span class="font-medium text-foreground">{{ review.customer_name }}</span>
              <span v-if="review.driver_name">·</span>
              <span v-if="review.driver_name">Re: {{ review.driver_name }}</span>
              <span>·</span>
              <span>{{ new Date(review.created_at).toLocaleDateString() }}</span>
              <span
                class="rounded-full px-2 py-0.5 font-medium"
                :class="review.is_approved ? 'bg-accent-bg/10 text-accent' : 'bg-red-500/10 text-danger'"
              >
                {{ review.is_approved ? 'Approved' : 'Pending' }}
              </span>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex shrink-0 flex-col gap-2 sm:flex-row">
            <button
              v-if="!review.is_approved"
              :disabled="busyId === review.id"
              class="rounded-md bg-accent-bg px-3 py-1.5 text-sm font-semibold text-on-accent hover:bg-accent-bg-hover disabled:opacity-50"
              @click="approve(review)"
            >
              Approve
            </button>
            <button
              v-if="review.is_approved"
              :disabled="busyId === review.id"
              class="rounded-md border border-border px-3 py-1.5 text-sm font-semibold text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
              @click="reject(review)"
            >
              Revoke
            </button>
            <button
              v-if="auth.user?.is_superuser"
              :disabled="busyId === review.id"
              class="rounded-md border border-danger-border px-3 py-1.5 text-sm font-semibold text-danger hover:bg-red-400 hover:text-on-accent disabled:opacity-50"
              @click="deleteReview(review)"
            >
              Delete
            </button>
          </div>
        </div>
      </div>

      <p v-if="!filteredReviews.length" class="py-10 text-center text-foreground-muted">
        {{ filter === 'pending' ? 'No pending reviews — all caught up! 🎉' : 'No reviews in this view.' }}
      </p>

      <div v-if="nextUrl" class="text-center pt-2">
        <button
          :disabled="loadingMore"
          class="rounded-md border border-border px-4 py-1.5 text-sm font-medium text-foreground-secondary hover:border-accent-border hover:text-accent disabled:opacity-50"
          @click="loadMore"
        >
          {{ loadingMore ? 'Loading...' : 'Load More' }}
        </button>
      </div>
    </div>
  </div>
</template>
