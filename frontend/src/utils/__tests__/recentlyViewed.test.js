import { beforeEach, describe, expect, it } from 'vitest'

import { getRecentlyViewedIds, recordVehicleView } from '../recentlyViewed'

describe('recentlyViewed', () => {
  beforeEach(() => localStorage.clear())

  it('returns an empty list when nothing has been viewed', () => {
    expect(getRecentlyViewedIds()).toEqual([])
  })

  it('records views most-recent-first', () => {
    recordVehicleView(1)
    recordVehicleView(2)
    recordVehicleView(3)
    expect(getRecentlyViewedIds()).toEqual([3, 2, 1])
  })

  it('moves an already-viewed vehicle to the front instead of duplicating it', () => {
    recordVehicleView(1)
    recordVehicleView(2)
    recordVehicleView(1)
    expect(getRecentlyViewedIds()).toEqual([1, 2])
  })

  it('caps the list at 8 entries', () => {
    for (let i = 1; i <= 10; i++) recordVehicleView(i)
    const ids = getRecentlyViewedIds()
    expect(ids).toHaveLength(8)
    expect(ids[0]).toBe(10)
  })

  it('excludes the given id', () => {
    recordVehicleView(1)
    recordVehicleView(2)
    expect(getRecentlyViewedIds(2)).toEqual([1])
  })

  it('never throws when localStorage is unavailable', () => {
    const original = window.localStorage
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: () => {
          throw new Error('blocked')
        },
        setItem: () => {
          throw new Error('blocked')
        },
      },
      configurable: true,
    })
    expect(() => recordVehicleView(1)).not.toThrow()
    expect(getRecentlyViewedIds()).toEqual([])
    Object.defineProperty(window, 'localStorage', { value: original, configurable: true })
  })
})
