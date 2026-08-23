import { describe, expect, it } from 'vitest'

import { discoveryErrorMessage } from './usePowerBIAgent'

describe('semantic-model discovery errors', () => {
  it('explains the multiple Desktop fail-closed state without diagnostics', () => {
    const message = discoveryErrorMessage('powerbi_multiple_desktop_instances')

    expect(message).toBe(
      '检测到多个 Power BI Desktop 模型，请只保留一个需要分析的 PBIX 后重试。',
    )
    expect(message).not.toMatch(/localhost|process|connection|string|mcp/i)
  })

  it('keeps existing disconnected and generic messages stable', () => {
    expect(discoveryErrorMessage('powerbi_desktop_not_connected')).toContain(
      'Power BI Desktop 未连接',
    )
    expect(discoveryErrorMessage('unknown_error')).toBe(
      '暂时无法获取可用数据模型。',
    )
  })
})
