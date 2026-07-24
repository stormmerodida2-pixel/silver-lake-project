import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/client', () => ({
  default: { get: vi.fn() },
}))

import apiClient from '../../api/client'
import { useCatalogStore } from '../catalog'

describe('useCatalogStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('fetchVehicles() always refetches, even if already called before', async () => {
    apiClient.get.mockResolvedValue({ data: { results: [{ id: 1 }] } })
    const catalog = useCatalogStore()

    await catalog.fetchVehicles()
    await catalog.fetchVehicles()

    expect(apiClient.get).toHaveBeenCalledTimes(2)
  })

  it('fetchDrivers() only fetches once - a second call is a no-op', async () => {
    apiClient.get.mockResolvedValue({ data: { results: [{ id: 1, full_name: 'Kip' }] } })
    const catalog = useCatalogStore()

    await catalog.fetchDrivers()
    await catalog.fetchDrivers()

    expect(apiClient.get).toHaveBeenCalledTimes(1)
    expect(catalog.drivers).toEqual([{ id: 1, full_name: 'Kip' }])
  })

  it('fetchReviews() and fetchCategories() each cache independently of one another', async () => {
    apiClient.get.mockResolvedValue({ data: { results: [] } })
    const catalog = useCatalogStore()

    await catalog.fetchReviews()
    await catalog.fetchCategories()
    await catalog.fetchReviews()
    await catalog.fetchCategories()

    expect(apiClient.get).toHaveBeenCalledTimes(2)
  })

  it('fetchBlogPosts() with no category caches once, like drivers/reviews', async () => {
    apiClient.get.mockResolvedValue({ data: { results: [{ id: 1 }], next: null } })
    const catalog = useCatalogStore()

    await catalog.fetchBlogPosts()
    await catalog.fetchBlogPosts()

    expect(apiClient.get).toHaveBeenCalledTimes(1)
  })

  it('fetchBlogPosts() with a category always refetches and does not poison the unfiltered cache', async () => {
    apiClient.get.mockResolvedValue({ data: { results: [{ id: 1 }], next: null } })
    const catalog = useCatalogStore()

    await catalog.fetchBlogPosts('travel-tips')
    await catalog.fetchBlogPosts('travel-tips')
    expect(apiClient.get).toHaveBeenCalledTimes(2)

    // Still not marked as loaded overall - an unfiltered call right after should still fetch.
    await catalog.fetchBlogPosts()
    expect(apiClient.get).toHaveBeenCalledTimes(3)
  })

  it('loadMoreBlogPosts() appends to the existing list and advances the cursor', async () => {
    apiClient.get
      .mockResolvedValueOnce({ data: { results: [{ id: 1 }], next: '/blog/?page=2' } })
      .mockResolvedValueOnce({ data: { results: [{ id: 2 }], next: null } })
    const catalog = useCatalogStore()

    await catalog.fetchBlogPosts()
    await catalog.loadMoreBlogPosts()

    expect(catalog.blogPosts).toEqual([{ id: 1 }, { id: 2 }])
    expect(catalog.blogPostsNextUrl).toBeNull()
  })

  it('loadMoreBlogPosts() is a no-op once there is no next page', async () => {
    apiClient.get.mockResolvedValue({ data: { results: [{ id: 1 }], next: null } })
    const catalog = useCatalogStore()
    await catalog.fetchBlogPosts()
    vi.clearAllMocks()

    await catalog.loadMoreBlogPosts()

    expect(apiClient.get).not.toHaveBeenCalled()
  })
})
