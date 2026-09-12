import { defineStore } from 'pinia'

import apiClient from '../api/client'

export const useCatalogStore = defineStore('catalog', {
  state: () => ({
    vehicles: [],
    drivers: [],
    reviews: [],
    categories: [],
    protectionPlans: [],
    blogPosts: [],
    blogPostsNextUrl: null,
    loaded: {
      drivers: false,
      reviews: false,
      categories: false,
      protectionPlans: false,
      blogPosts: false,
    },
    // Tracks in-flight fetches for vehicles/drivers/reviews only - the listing views that show
    // an explicit "No X yet" empty state, which would otherwise flash true for a moment on every
    // load before the fetch resolves. `loaded` above answers "do we have data", this answers
    // "are we currently fetching" - the two are different questions (e.g. a request that legitimately
    // returns zero results is `loaded` but not `loading`).
    loading: {
      vehicles: false,
      drivers: false,
      reviews: false,
    },
  }),
  actions: {
    // Always refetched (unlike drivers/reviews) so vehicles an admin just added or
    // changed show up immediately for users already browsing the site.
    async fetchVehicles() {
      this.loading.vehicles = true
      try {
        const { data } = await apiClient.get('/vehicles/')
        this.vehicles = data.results ?? data
      } finally {
        this.loading.vehicles = false
      }
    },
    async fetchDrivers() {
      if (this.loaded.drivers) return
      this.loading.drivers = true
      try {
        const { data } = await apiClient.get('/drivers/')
        this.drivers = data.results ?? data
        this.loaded.drivers = true
      } finally {
        this.loading.drivers = false
      }
    },
    async fetchReviews() {
      if (this.loaded.reviews) return
      this.loading.reviews = true
      try {
        const { data } = await apiClient.get('/reviews/')
        this.reviews = data.results ?? data
        this.loaded.reviews = true
      } finally {
        this.loading.reviews = false
      }
    },
    // Fleet types (e.g. "Executive SUV") - admin-managed, so this isn't cached as
    // aggressively as drivers/reviews; still cheap enough to just fetch once per session.
    async fetchCategories() {
      if (this.loaded.categories) return
      const { data } = await apiClient.get('/categories/')
      this.categories = data.results ?? data
      this.loaded.categories = true
    },
    // Protection plan tiers (e.g. "Standard") - admin-managed, cached once per session like
    // categories.
    async fetchProtectionPlans() {
      if (this.loaded.protectionPlans) return
      const { data } = await apiClient.get('/protection-plans/')
      this.protectionPlans = data.results ?? data
      this.loaded.protectionPlans = true
    },
    // Marketing content, published in advance - doesn't need vehicles' always-refetch
    // freshness, so an unfiltered fetch is cached once per session like drivers/reviews/
    // categories. A category filter always re-fetches, though - filtering has to happen
    // server-side (not over the cached array) so it stays correct once combined with
    // pagination, since the cache may only hold the first page.
    async fetchBlogPosts(category = '') {
      if (!category && this.loaded.blogPosts) return
      const { data } = await apiClient.get('/blog/', category ? { params: { category } } : undefined)
      this.blogPosts = data.results ?? data
      this.blogPostsNextUrl = data.next ?? null
      if (!category) this.loaded.blogPosts = true
    },
    async loadMoreBlogPosts() {
      if (!this.blogPostsNextUrl) return
      const { data } = await apiClient.get(this.blogPostsNextUrl)
      this.blogPosts = this.blogPosts.concat(data.results ?? [])
      this.blogPostsNextUrl = data.next ?? null
    },
  },
})
