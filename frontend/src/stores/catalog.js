import { defineStore } from 'pinia'

import apiClient from '../api/client'

export const useCatalogStore = defineStore('catalog', {
  state: () => ({
    vehicles: [],
    drivers: [],
    reviews: [],
    loaded: {
      vehicles: false,
      drivers: false,
      reviews: false,
    },
  }),
  actions: {
    async fetchVehicles() {
      if (this.loaded.vehicles) return
      const { data } = await apiClient.get('/vehicles/')
      this.vehicles = data.results ?? data
      this.loaded.vehicles = true
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
  },
})
