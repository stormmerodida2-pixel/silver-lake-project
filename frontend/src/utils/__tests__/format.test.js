import { describe, expect, it } from 'vitest'

import { ordinal } from '../format'

describe('ordinal', () => {
  it('formats the common cases', () => {
    expect(ordinal(1)).toBe('1st')
    expect(ordinal(2)).toBe('2nd')
    expect(ordinal(3)).toBe('3rd')
    expect(ordinal(4)).toBe('4th')
    expect(ordinal(10)).toBe('10th')
  })

  it('handles the 11-13 exceptions', () => {
    expect(ordinal(11)).toBe('11th')
    expect(ordinal(12)).toBe('12th')
    expect(ordinal(13)).toBe('13th')
  })

  it('handles the twenties correctly (21st, not 21th)', () => {
    expect(ordinal(21)).toBe('21st')
    expect(ordinal(22)).toBe('22nd')
    expect(ordinal(23)).toBe('23rd')
    expect(ordinal(100)).toBe('100th')
    expect(ordinal(111)).toBe('111th')
  })
})
