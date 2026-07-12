import { defineStore } from 'pinia'

import apiClient from '../api/client'

export const useCatalogStore = defineStore('catalog', {
  state: () => ({
    vehicles: [],
    drivers: [],
    reviews: [],
    categories: [],
    loaded: {
      drivers: false,
      reviews: false,
      categories: false,
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
  },
})
