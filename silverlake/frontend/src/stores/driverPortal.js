import { defineStore } from 'pinia'

import apiClient from '../api/client'

/**
 * Shared profile + bookings data for the Driver Portal's three pages (Dashboard, My Vehicles,
 * My Bookings) - centralized here rather than each page fetching its own copy, so a mutation on
 * one page (e.g. completing a trip on the Bookings page) is instantly reflected everywhere else
 * that reads the same booking/vehicle (e.g. the Dashboard's stat tiles), since they're the same
 * in-memory objects, not separate copies.
 */
export const useDriverPortalStore = defineStore('driverPortal', {
  state: () => ({
    profile: null,
    profileLoading: true,
    profileError: '',
    bookings: [],
    bookingsLoading: true,
    bookingsError: '',
    hasLoaded: false,
  }),
  getters: {
    initials: (state) => {
      const name = state.profile?.full_name || ''
      const parts = name.trim().split(/\s+/).filter(Boolean)
      return (parts[0]?.[0] || '') + (parts[1]?.[0] || '')
    },
    pendingBookingsCount: (state) => state.bookings.filter((b) => !b.driver_acknowledged_at).length,
    activeTripsCount: (state) => state.bookings.filter((b) => ['confirmed', 'ongoing'].includes(b.status)).length,
    completedTripsCount: (state) => state.bookings.filter((b) => b.status === 'completed').length,
    serviceDueCount: (state) => (state.profile?.vehicles || []).filter((v) => v.is_service_due).length,
  },
  actions: {
    async loadProfile() {
      this.profileLoading = true
      this.profileError = ''
      try {
        const { data } = await apiClient.get('/driver/me/')
        this.profile = data
      } catch (err) {
        this.profileError = 'Could not load your driver profile.'
      } finally {
        this.profileLoading = false
      }
    },
    async loadBookings() {
      this.bookingsLoading = true
      this.bookingsError = ''
      try {
        const { data } = await apiClient.get('/driver/bookings/mine/')
        this.bookings = data.results ?? data
      } catch (err) {
        this.bookingsError = 'Could not load your bookings.'
      } finally {
        this.bookingsLoading = false
      }
    },
    async loadAll() {
      if (this.hasLoaded) return
      await Promise.all([this.loadProfile(), this.loadBookings()])
      this.hasLoaded = true
    },
    async markAway(reason) {
      const { data } = await apiClient.patch('/driver/away/', { is_away: true, away_reason: reason })
      this.profile = data
    },
    async markAvailable() {
      const { data } = await apiClient.patch('/driver/away/', { is_away: false, away_reason: '' })
      this.profile = data
    },
    addVehicleSubmission(submission) {
      this.profile.vehicle_submissions.unshift(submission)
    },
    addServiceRecord(vehicleId, record) {
      const vehicle = this.profile.vehicles.find((v) => v.id === vehicleId)
      if (vehicle) vehicle.service_records = [record, ...(vehicle.service_records || [])]
    },
    addBooking(booking) {
      this.bookings.unshift(booking)
    },
  },
})
