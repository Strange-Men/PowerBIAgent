import { describe, expect, it } from 'vitest'
import { chatResponseToMessage, historyItemToMessages, isUsableReport } from './adapters'
import type { ChatResponse, ReportResource } from '../types'

function response(overrides: Partial<ChatResponse> = {}): ChatResponse {
  return {
    request_id: 'req-1',
    conversation_id: 'conv-1',
    terminal_state: 'completed',
    intent: 'data_query',
    response_type: 'answer',
    answer: '销售额为 100。',
    report: null,
    clarification_question: null,
    unsupported_reason: null,
    error_type: null,
    source_mode: 'real',
    idempotent_replay: false,
    ...overrides,
  }
}

describe('chatResponseToMessage', () => {
  it('renders a normal answer without inventing extra content blocks', () => {
    expect(chatResponseToMessage(response())).toEqual({
      id: 'req-1',
      role: 'assistant',
      kind: 'answer',
      content: '销售额为 100。',
    })
  })

  it('uses clarification and unsupported fields for their terminal branches', () => {
    expect(
      chatResponseToMessage(
        response({
          terminal_state: 'clarification_required',
          response_type: 'clarification',
          answer: null,
          clarification_question: '你想按哪个区域查看？',
        }),
      ).content,
    ).toBe('你想按哪个区域查看？')

    expect(
      chatResponseToMessage(
        response({
          terminal_state: 'unsupported',
          response_type: 'unsupported',
          answer: null,
          unsupported_reason: '当前不支持跨模型查询。',
        }),
      ).kind,
    ).toBe('unsupported')
  })

  it('uses a natural empty response instead of fake data', () => {
    const message = chatResponseToMessage(response({ answer: null }))
    expect(message.kind).toBe('empty')
    expect(message.content).toContain('暂无符合条件的数据')
    expect(message.report).toBeUndefined()
  })

  it('does not expose an internal error type as message content', () => {
    const message = chatResponseToMessage(
      response({
        terminal_state: 'response_failed',
        response_type: 'error',
        answer: null,
        error_type: 'internal_python_stack_marker',
      }),
    )
    expect(message.kind).toBe('error')
    expect(message.content).not.toContain('internal_python_stack_marker')
  })

  it('distinguishes Desktop and model availability failures without raw errors', () => {
    const desktop = chatResponseToMessage(
      response({
        terminal_state: 'tool_failed',
        response_type: 'error',
        answer: null,
        error_type: 'connection_error',
        powerbi_mode: 'local_mcp',
      }),
    )
    expect(desktop.content).toContain('Power BI Desktop')
    expect(desktop.content).not.toContain('connection_error')

    const genericToolFailure = chatResponseToMessage(
      response({
        terminal_state: 'tool_failed',
        response_type: 'error',
        answer: null,
        error_type: 'ToolExecutionError',
        powerbi_mode: 'local_mcp',
      }),
    )
    expect(genericToolFailure.content).toContain('当前请求无法完成')
    expect(genericToolFailure.content).not.toContain('Power BI Desktop')

    const model = chatResponseToMessage(
      response({
        terminal_state: 'tool_failed',
        response_type: 'error',
        answer: null,
        error_type: 'ToolPolicyDeniedError',
      }),
    )
    expect(model.content).toContain('数据模型不可用')
    expect(model.content).not.toContain('ToolPolicyDeniedError')
  })

  it('maps a stale Desktop selection to a safe refresh instruction', () => {
    const message = chatResponseToMessage(
      response({
        terminal_state: 'tool_failed',
        response_type: 'error',
        answer: null,
        error_type: 'stale_instance',
        powerbi_mode: 'local_mcp',
      }),
    )

    expect(message.content).toContain('刷新模型列表后重新选择')
    expect(message.content).not.toContain('stale_instance')
  })

  it('maps provider failures to a safe language-service message', () => {
    const message = chatResponseToMessage(
      response({
        terminal_state: 'validation_failed',
        response_type: 'error',
        answer: null,
        error_type: 'LLMConnectionError',
      }),
    )
    expect(message.content).toContain('语言分析服务暂不可用')
    expect(message.content).not.toContain('LLMConnectionError')
  })

  it.each([
    ['llm_service_unavailable', '语言分析服务暂不可用'],
    ['mcp_timeout', 'Power BI 响应超时'],
    ['mcp_connection_failed', '无法连接 Power BI Desktop'],
    ['dax_execution_failed', 'Power BI 查询执行失败'],
  ])('maps stable error type %s to safe Chinese copy', (errorType, expected) => {
    const message = chatResponseToMessage(
      response({
        terminal_state: 'tool_failed',
        response_type: 'error',
        answer: null,
        error_type: errorType,
      }),
    )

    expect(message.content).toContain(expected)
    expect(message.content).not.toContain(errorType)
  })
})

describe('report resource validation', () => {
  const report: ReportResource = {
    report_id: 'report-1',
    template_key: 'sales_report',
    contract_version: '2.0',
    view_reference: '/api/reports/report-1',
    download_reference: '/api/reports/report-1/download',
    content_type: 'text/html; charset=utf-8',
    content_hash: 'hash',
  }

  it('accepts only the backend canonical report references', () => {
    expect(isUsableReport(report)).toBe(true)
    expect(isUsableReport({ ...report, view_reference: 'https://example.com/report' })).toBe(
      false,
    )
  })

  it('adds the attachment only when the report resource is valid', () => {
    expect(chatResponseToMessage(response({ report })).report).toEqual(report)
    expect(
      chatResponseToMessage(
        response({ report: { ...report, download_reference: 'javascript:alert(1)' } }),
      ).report,
    ).toBeUndefined()
  })
})

describe('history transcript projection', () => {
  it('restores the declared user message before the assistant result', () => {
    const messages = historyItemToMessages({
      request_id: 'req-history',
      created_at: '2026-08-23T10:00:00',
      terminal_state: 'completed',
      response_type: 'answer',
      intent: 'data_question',
      user_message: '查看华东销售额',
      answer: '华东销售额为 100。',
      report: null,
      clarification_question: null,
      unsupported_reason: null,
      error_type: null,
    })
    expect(messages).toHaveLength(2)
    expect(messages[0]).toMatchObject({ role: 'user', content: '查看华东销售额' })
    expect(messages[1]).toMatchObject({ role: 'assistant', restored: true })
  })

  it('restores a deleted report as a tombstone even without artifact links', () => {
    const deleted: ReportResource = {
      report_id: 'report-deleted',
      template_key: 'sales_report',
      contract_version: '2.0',
      display_title: '删除前标题',
      availability_status: 'deleted',
      view_reference: '',
      download_reference: '',
      content_type: 'text/html; charset=utf-8',
      content_hash: '',
    }
    expect(chatResponseToMessage(response({ report: deleted })).report).toEqual(
      deleted,
    )
    expect(isUsableReport(deleted)).toBe(false)
  })
})
