import { describe, expect, it } from 'vitest'
import { formatRemaining } from './util'

describe('formatRemaining', () => {
  it('counts down and reports expiry', () => {
    const now = Date.parse('2026-09-14T12:00:00Z')
    expect(formatRemaining('2026-09-14T12:14:30Z', now)).toBe('14m 30s')
    expect(formatRemaining('2026-09-14T11:59:59Z', now)).toBe('expired')
    expect(formatRemaining('garbage', now)).toBe('unknown')
  })
})
