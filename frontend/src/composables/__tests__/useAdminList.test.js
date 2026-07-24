import { reactive } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/client', () => ({
  default: { get: vi.fn() },
}))

import apiClient from '../../api/client'
import { useAdminList } from '../useAdminList'

describe('useAdminList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('load() populates items and captures the next-page cursor', async () => {
    apiClient.get.mockResolvedValue({ data: { results: [{ id: 1 }, { id: 2 }], next: '/admin/bookings/?page=2' } })
    const { items, nextUrl, loading, load } = useAdminList('/admin/bookings/')

    await load()

    expect(items.value).toEqual([{ id: 1 }, { id: 2 }])
    expect(nextUrl.value).toBe('/admin/bookings/?page=2')
    expect(loading.value).toBe(false)
  })

  it('load() also handles a plain (non-paginated) array response', async () => {
    apiClient.get.mockResolvedValue({ data: [{ id: 1 }] })
    const { items, nextUrl, load } = useAdminList('/admin/drivers/')

    await load()

    expect(items.value).toEqual([{ id: 1 }])
    expect(nextUrl.value).toBeNull()
  })

  it('load() surfaces a friendly error and stops loading on failure', async () => {
    apiClient.get.mockRejectedValue(new Error('network error'))
    const { error, loading, load } = useAdminList('/admin/bookings/')

    await load()

    expect(error.value).toBe('Could not load data.')
    expect(loading.value).toBe(false)
  })

  it('loadMore() appends results and is a no-op with no next page', async () => {
    apiClient.get
      .mockResolvedValueOnce({ data: { results: [{ id: 1 }], next: '/admin/bookings/?page=2' } })
      .mockResolvedValueOnce({ data: { results: [{ id: 2 }], next: null } })
    const { items, nextUrl, load, loadMore } = useAdminList('/admin/bookings/')

    await load()
    await loadMore()
    expect(items.value).toEqual([{ id: 1 }, { id: 2 }])
    expect(nextUrl.value).toBeNull()

    vi.clearAllMocks()
    await loadMore()
    expect(apiClient.get).not.toHaveBeenCalled()
  })

  it('debounces a reactive filter change into a single reload, not one per keystroke', async () => {
    apiClient.get.mockResolvedValue({ data: { results: [], next: null } })
    const filters = reactive({ search: '' })
    const { load } = useAdminList('/admin/bookings/', filters)
    await load()
    vi.clearAllMocks()

    filters.search = 'a'
    filters.search = 'al'
    filters.search = 'ali'
    await vi.advanceTimersByTimeAsync(299)
    expect(apiClient.get).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(10)
    expect(apiClient.get).toHaveBeenCalledTimes(1)
    expect(apiClient.get).toHaveBeenCalledWith('/admin/bookings/', { params: filters })
  })

  it('passes filters through as query params on the initial load too', async () => {
    apiClient.get.mockResolvedValue({ data: { results: [], next: null } })
    const filters = reactive({ status: 'active' })
    const { load } = useAdminList('/admin/bookings/', filters)

    await load()

    expect(apiClient.get).toHaveBeenCalledWith('/admin/bookings/', { params: filters })
  })
})
