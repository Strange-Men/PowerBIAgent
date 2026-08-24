import { describe, expect, it, vi } from 'vitest'
import { runBoundedBatch } from './usePowerBIAgent'

describe('runBoundedBatch', () => {
  it('executes 40 selected resources in bounded waves of at most 20', async () => {
    const ids = Array.from({ length: 40 }, (_, index) => `resource-${index + 1}`)
    let active = 0
    let maximumActive = 0
    const operation = vi.fn(async () => {
      active += 1
      maximumActive = Math.max(maximumActive, active)
      await Promise.resolve()
      active -= 1
    })

    const result = await runBoundedBatch(ids, operation)

    expect(result).toEqual({ succeededIds: ids, failed: [] })
    expect(operation).toHaveBeenCalledTimes(40)
    expect(maximumActive).toBe(20)
  })

  it('continues later waves and reports each failed resource precisely', async () => {
    const ids = Array.from({ length: 41 }, (_, index) => `resource-${index + 1}`)
    const operation = vi.fn(async (id: string) => {
      if (id === 'resource-8' || id === 'resource-40') {
        throw new Error(`cannot delete ${id}`)
      }
    })

    const result = await runBoundedBatch(ids, operation)

    expect(result.succeededIds).toHaveLength(39)
    expect(result.failed).toEqual([
      { id: 'resource-8', reason: 'cannot delete resource-8' },
      { id: 'resource-40', reason: 'cannot delete resource-40' },
    ])
    expect(operation).toHaveBeenCalledTimes(41)
  })
})
