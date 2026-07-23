<script setup>
import { onMounted, ref } from 'vue'

import { useCatalogStore } from '../stores/catalog'
import BlogPostCard from '../components/BlogPostCard.vue'

const catalog = useCatalogStore()
const loadingMore = ref(false)
const activeCategory = ref('all')

const categories = [
  { value: 'all', label: 'All' },
  { value: 'travel_tips', label: 'Travel Tips' },
  { value: 'destination_guides', label: 'Destination Guides' },
  { value: 'fleet_spotlights', label: 'Fleet & Driver Spotlights' },
  { value: 'company_news', label: 'Company News' },
]

onMounted(() => {
  catalog.fetchBlogPosts()
})

function selectCategory(value) {
  activeCategory.value = value
  catalog.fetchBlogPosts(value === 'all' ? '' : value)
}

async function loadMore() {
  loadingMore.value = true
  try {
    await catalog.loadMoreBlogPosts()
  } finally {
    loadingMore.value = false
  }
}
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <h1 class="text-center font-[Georgia] text-3xl font-bold text-navy-900">Travel Tips & Guides</h1>
      <p class="mt-2 text-center text-slate-600">
        Destination guides, road-trip tips, and news from the SilverLake fleet.
      </p>

      <div class="mt-8 flex flex-wrap justify-center gap-2">
        <button
          v-for="cat in categories"
          :key="cat.value"
          class="rounded-full border px-4 py-1.5 text-sm font-medium transition"
          :class="
            activeCategory === cat.value
              ? 'border-brand-blue-600 bg-brand-blue-600 text-white'
              : 'border-slate-300 text-slate-600 hover:border-brand-blue-500 hover:text-brand-blue-600'
          "
          @click="selectCategory(cat.value)"
        >
          {{ cat.label }}
        </button>
      </div>

      <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <BlogPostCard v-for="post in catalog.blogPosts" :key="post.id" :post="post" />
      </div>

      <p v-if="!catalog.blogPosts.length" class="mt-10 text-center text-slate-500">No posts yet - check back soon.</p>

      <div v-if="catalog.blogPostsNextUrl" class="mt-10 text-center">
        <button
          :disabled="loadingMore"
          class="rounded-full border border-brand-blue-600 px-6 py-2 text-sm font-semibold text-brand-blue-600 transition hover:bg-brand-blue-600 hover:text-white disabled:opacity-50"
          @click="loadMore"
        >
          {{ loadingMore ? 'Loading…' : 'Load More' }}
        </button>
      </div>
    </div>
  </div>
</template>
