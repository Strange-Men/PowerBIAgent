import { describe, expect, it } from 'vitest'

import type { SemanticModelOption } from '../types'
import {
  catalogOptions,
  discoveryErrorMessage,
  reconcileSemanticModelSelection,
  withoutDeletedReport,
} from './usePowerBIAgent'

describe('semantic-model discovery errors', () => {
  it('explains only duplicate Desktop identity failure without diagnostics', () => {
    const message = discoveryErrorMessage('powerbi_multiple_desktop_instances')

    expect(message).toBe(
      '检测到重复的 Desktop 实例身份，已安全停止模型发现。',
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

describe('semantic-model catalog selection', () => {
  const item = (
    key: string,
    displayName: string,
  ): SemanticModelOption => ({
    key,
    display_name: displayName,
    source: 'local_desktop',
    type: 'semantic_model',
    available: true,
    connected: true,
    agent_compatible: true,
    selectable: true,
    schema_drift: false,
    compatibility_status: 'compatible',
  })

  it('shows every Desktop model and distinguishes duplicate display names safely', () => {
    const options = catalogOptions([
      item('local_desktop:aaaa', '销售模型'),
      item('local_desktop:bbbb', '销售模型'),
      item('local_desktop:cccc', '库存模型'),
    ])

    expect(options.map((option) => option.label)).toEqual([
      '销售模型（实例 1）',
      '销售模型（实例 2）',
      '库存模型',
    ])
    expect(options.map((option) => option.key)).toEqual([
      'local_desktop:aaaa',
      'local_desktop:bbbb',
      'local_desktop:cccc',
    ])
    expect(options.map((option) => option.label).join(' ')).not.toContain(
      'local_desktop:',
    )
  })

  it('keeps an exact selected key and never switches a stale selection', () => {
    const firstOptions = catalogOptions([
      item('local_desktop:aaaa', 'Rich'),
      item('local_desktop:bbbb', 'Simple'),
    ])
    expect(
      reconcileSemanticModelSelection(firstOptions[1], firstOptions, false),
    ).toEqual({ selected: firstOptions[1], stale: false })

    const refreshed = catalogOptions([
      item('local_desktop:cccc', 'Rich'),
    ])
    expect(
      reconcileSemanticModelSelection(firstOptions[1], refreshed, false),
    ).toEqual({ selected: null, stale: true })
    expect(reconcileSemanticModelSelection(null, refreshed, false)).toEqual({
      selected: null,
      stale: false,
    })
  })
})

describe('independent report removal projection', () => {
  it('removes only the deleted attachment and leaves the conversation text', () => {
    const messages = withoutDeletedReport([
      { id: 'user-1', role: 'user', content: '生成报告' },
      {
        id: 'assistant-1',
        role: 'assistant',
        kind: 'answer',
        content: '报告已生成',
        report: {
          report_id: 'rpt-1',
          template_key: 'sales_report',
          contract_version: '1.0',
          view_reference: '/api/reports/rpt-1',
          download_reference: '/api/reports/rpt-1/download',
          content_type: 'text/html; charset=utf-8',
          content_hash: 'a'.repeat(64),
        },
        presentation: {
          version: 1,
          datasets: [],
          blocks: [
            { type: 'text', content: '报告已生成' },
            { type: 'report_attachment', report_id: 'rpt-1' },
          ],
        },
      },
    ], 'rpt-1')

    expect(messages).toHaveLength(2)
    expect(messages[1]).not.toHaveProperty('report')
    expect(messages[1]).toMatchObject({ content: '报告已生成' })
  })
})
