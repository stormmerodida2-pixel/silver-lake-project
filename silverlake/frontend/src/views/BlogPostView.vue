<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import apiClient from '../api/client'
import { useCatalogStore } from '../stores/catalog'
import { setPageMeta } from '../utils/seo'

const route = useRoute()
const router = useRouter()
const catalog = useCatalogStore()

const post = ref(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  // Try catalog cache first (from the list page), fall back to a direct API call - a direct
  // permalink hit from a search engine won't have gone through /blog first.
  await catalog.fetchBlogPosts()
  const cached = catalog.blogPosts.find((p) => p.slug === route.params.slug)
  if (cached) {
    post.value = cached
    loading.value = false
  } else {
    try {
      const { data } = await apiClient.get(`/blog/${route.params.slug}/`)
      post.value = data
    } catch (err) {
      if (err.response?.status === 404) {
        router.replace('/blog')
      } else {
        error.value = 'Could not load this post.'
      }
    } finally {
      loading.value = false
    }
  }

  // Overrides the generic /blog/:slug title the router set on navigation - a shared link now
  // gets the post's own title/excerpt/cover image in the tab, search results, and chat previews.
  if (post.value) {
    setPageMeta({
      title: `${post.value.title} | SilverLake Car Rentals Blog`,
      description: post.value.excerpt,
      image: post.value.cover_image,
      type: 'article',
    })
  }
})
</script>

<template>
  <div class="bg-white">
    <p v-if="loading" class="py-32 text-center text-slate-500">Loading...</p>
    <p v-else-if="error" class="py-32 text-center text-red-600">{{ error }}</p>

    <template v-else-if="post">
      <div class="relative h-72 w-full bg-slate-100 sm:h-96">
        <img
          v-if="post.cover_image"
          :src="post.cover_image"
          :alt="post.title"
          class="h-full w-full object-cover"
        />
        <div v-else class="flex h-full items-center justify-center text-lg text-slate-300">SilverLake Car Rentals</div>
        <RouterLink
          to="/blog"
          class="absolute top-4 left-4 flex items-center gap-1.5 rounded-full bg-white/90 px-4 py-2 text-sm font-semibold text-navy-900 shadow backdrop-blur hover:bg-white"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          All Posts
        </RouterLink>
      </div>

      <div class="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <div v-if="!post.is_published" class="mb-6 rounded-lg border border-gold-500 bg-gold-500/10 px-4 py-3 text-sm font-semibold text-gold-700">
          Draft preview — this post is not published yet and isn't visible to the public.
        </div>
        <div class="flex items-center gap-2">
          <span v-if="post.category_display" class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
            {{ post.category_display }}
          </span>
          <p v-if="post.published_at" class="text-sm font-semibold uppercase tracking-widest text-brand-blue-600">
            {{ new Date(post.published_at).toLocaleDateString('en-KE', { year: 'numeric', month: 'long', day: 'numeric' }) }}
          </p>
        </div>
        <h1 class="mt-2 font-[Georgia] text-3xl font-bold text-navy-900 sm:text-4xl">{{ post.title }}</h1>
        <p class="mt-2 text-sm text-slate-500">By SilverLake Car Rentals Team</p>

        <div class="prose mt-8 max-w-none text-slate-700" v-html="post.body"></div>
      </div>
    </template>
  </div>
</template>
