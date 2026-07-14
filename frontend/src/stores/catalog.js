import { defineStore } from 'pinia'

import apiClient from '../api/client'

export const useCatalogStore = defineStore('catalog', {
  state: () => ({
    vehicles: [],
    drivers: [],
    reviews: [],
    categories: [],
    blogPosts: [],
    blogPostsNextUrl: null,
    loaded: {
      drivers: false,
      reviews: false,
      categories: false,
      blogPosts: false,
    },
  }),
  actions: {
    // Always refetched (unlike drivers/reviews) so vehicles an admin just added or
    // changed show up immediately for users already browsing the site.
    async fetchVehicles() {
      const { data } = await apiClient.get('/vehicles/')
      this.vehicles = data.results ?? data
    },
    async fetchDrivers() {
      if (this.loaded.drivers) return
      const { data } = await apiClient.get('/drivers/')
      this.drivers = data.results ?? data
      this.loaded.drivers = true
    },
    async fetchReviews() {
      if (this.loaded.reviews) return
      const { data } = await apiClient.get('/reviews/')
      this.reviews = data.results ?? data
      this.loaded.reviews = true
    },
    // Fleet types (e.g. "Executive SUV") - admin-managed, so this isn't cached as
    // aggressively as drivers/reviews; still cheap enough to just fetch once per session.
    async fetchCategories() {
      if (this.loaded.categories) return
      const { data } = await apiClient.get('/categories/')
      this.categories = data.results ?? data
      this.loaded.categories = true
    },
    // Marketing content, published in advance - doesn't need vehicles' always-refetch
    // freshness, so it's cached once per session like drivers/reviews/categories.
    async fetchBlogPosts() {
      if (this.loaded.blogPosts) return
      const { data } = await apiClient.get('/blog/')
      this.blogPosts = data.results ?? data
      this.blogPostsNextUrl = data.next ?? null
      this.loaded.blogPosts = true
    },
    async loadMoreBlogPosts() {
      if (!this.blogPostsNextUrl) return
      const { data } = await apiClient.get(this.blogPostsNextUrl)
      this.blogPosts = this.blogPosts.concat(data.results ?? [])
      this.blogPostsNextUrl = data.next ?? null
    },
  },
})
