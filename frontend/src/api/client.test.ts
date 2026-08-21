import { afterEach, describe, expect, it, vi } from 'vitest'
import { listRecentConversations, sendChat } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('API namespace and chat mapping', () => {
  it('sends the explicit runtime namespace for recent conversations', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ runtime_mode: 'real', items: [], next_cursor: null }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listRecentConversations('real', 12)

    expect(fetchMock.mock.calls[0][0]).toContain(
      '/api/v1/conversations?runtime_mode=real&limit=12',
    )
  })

  it('maps composer selections to the real chat request fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          request_id: 'req-1',
          conversation_id: 'conv-1',
          terminal_state: 'completed',
          intent: 'report',
          response_type: 'report',
          answer: null,
          report: null,
          clarification_question: null,
          unsupported_reason: null,
          error_type: null,
          source_mode: 'real',
          idempotent_replay: false,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await sendChat({
      message: '生成销售报表',
      request_id: 'req-1',
      conversation_id: 'conv-1',
      semantic_model_key: 'local_desktop_model',
      report_template_key: 'sales_report',
    })

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(init.body))).toEqual({
      message: '生成销售报表',
      request_id: 'req-1',
      conversation_id: 'conv-1',
      semantic_model_key: 'local_desktop_model',
      report_template_key: 'sales_report',
    })
  })
})
