<script setup>
import { onMounted } from 'vue'

import { useCatalogStore } from '../stores/catalog'
import BlogPostCard from '../components/BlogPostCard.vue'

const catalog = useCatalogStore()

onMounted(() => {
  catalog.fetchBlogPosts()
})
</script>

<template>
  <div class="bg-white">
    <div class="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <h1 class="text-center font-[Georgia] text-3xl font-bold text-navy-900">Travel Tips & Guides</h1>
      <p class="mt-2 text-center text-slate-600">
        Destination guides, road-trip tips, and news from the SilverLake fleet.
      </p>

      <div class="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <BlogPostCard v-for="post in catalog.blogPosts" :key="post.id" :post="post" />
      </div>

      <p v-if="!catalog.blogPosts.length" class="mt-10 text-center text-slate-500">
        No posts yet - check back soon.
      </p>
    </div>
  </div>
</template>
