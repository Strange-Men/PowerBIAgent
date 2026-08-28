import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  archiveConversation,
  archiveReport,
  deleteConversation,
  deleteReport,
  discoverReportTemplates,
  discoverLLMProfiles,
  discoverSemanticModels,
  getConversationHistory,
  listArchivedConversations,
  listManagedReports,
  listRecentConversations,
  listRecentReports,
  recordFailedConversation,
  renameConversation,
  renameReport,
  restoreConversation,
  restoreReport,
  sendChat,
} from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('API namespace and chat mapping', () => {
  it('loads the backend-owned public LLM profile catalog', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await discoverLLMProfiles()
    expect(fetchMock.mock.calls[0][0]).toContain('/api/v1/llm-profiles')
  })

  it('sends the explicit runtime namespace for recent conversations', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ runtime_mode: 'real', items: [], next_cursor: null, total_count: 0 }),
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
      llm_profile_key: 'kimi-k2.6',
    })

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(init.body))).toEqual({
      message: '生成销售报表',
      request_id: 'req-1',
      conversation_id: 'conv-1',
      semantic_model_key: 'local_desktop_model',
      report_template_key: 'sales_report',
      llm_profile_key: 'kimi-k2.6',
    })
  })

  it('lists archived conversations through their recoverable namespace entry', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ runtime_mode: 'real', items: [], next_cursor: null, total_count: 0 }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    await listArchivedConversations('real')
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      '/api/v1/conversations/archived?runtime_mode=real',
    )
  })

  it('passes opaque cursors to independent Settings history queries', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          runtime_mode: 'real',
          items: [],
          next_cursor: null,
          total_count: 35,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listRecentConversations('real', 20, 'opaque-next-page')

    expect(String(fetchMock.mock.calls[0][0])).toContain('limit=20')
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      'cursor=opaque-next-page',
    )
  })

  it('uses the global source-scoped report lifecycle and pagination APIs', async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            source_mode: 'real',
            status: 'archived',
            items: [],
            next_cursor: null,
            total_count: 30,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listManagedReports('real', 'archived', 20, 'report-cursor')
    await archiveReport('real', 'rpt_' + 'a'.repeat(32))
    await restoreReport('real', 'rpt_' + 'a'.repeat(32))

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      '/api/reports?source_mode=real&status=archived&limit=20&cursor=report-cursor',
    )
    expect(String(fetchMock.mock.calls[1][0])).toContain(
      '/archive?source_mode=real',
    )
    expect(String(fetchMock.mock.calls[2][0])).toContain(
      '/restore?source_mode=real',
    )
  })

  it('omits the report template when the user did not choose an override', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          request_id: 'req-2',
          conversation_id: 'conv-2',
          terminal_state: 'completed',
          intent: 'data_question',
          response_type: 'answer',
          answer: '完成',
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
      message: '生成销售分析报告',
      request_id: 'req-2',
      semantic_model_key: 'local_desktop_model',
    })

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(init.body))).not.toHaveProperty('report_template_key')
  })

  it('loads semantic models from the read-only backend catalog', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ runtime_mode: 'real', items: [], error_type: null }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await discoverSemanticModels()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/semantic-models',
      expect.objectContaining({ headers: expect.any(Object) }),
    )
  })

  it('loads report templates from the backend-owned catalog', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [{
            template_key: 'sales_report',
            display_name: '简易模板',
            description: '适合快速查看关键指标、趋势与分类明细',
            availability: 'available',
          }],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await discoverReportTemplates()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/report-templates',
      expect.objectContaining({ headers: expect.any(Object) }),
    )
  })

  it('keeps report history inside the selected source namespace', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ source_mode: 'real', status: 'active', items: [], next_cursor: null, total_count: 0 }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listRecentReports('real')

    expect(String(fetchMock.mock.calls[0][0])).toBe(
      '/api/reports?source_mode=real&status=active&limit=8',
    )
  })

  it('records only safe failed-conversation resource metadata', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          runtime_mode: 'real',
          conversation_id: 'failed-conversation',
          resource_status: 'failed',
          last_error_type: 'client_request_failed',
          updated_at: '2026-08-26T10:00:00',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await recordFailedConversation('real', 'failed-conversation', {
      title: '失败问题',
      error_type: 'client_request_failed',
    })

    expect(String(fetchMock.mock.calls[0][0])).toBe(
      '/api/v1/conversations/failed-conversation/failure?runtime_mode=real',
    )
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({ title: '失败问题', error_type: 'client_request_failed' }),
    })
  })

  it('loads all bounded history pages for a complete restored conversation', async () => {
    const pages = [
      { runtime_mode: 'real', conversation_id: 'conv-1', archived_at: null, title: '完整历史', items: [{ request_id: 'new' }], next_cursor: 'older' },
      { runtime_mode: 'real', conversation_id: 'conv-1', archived_at: null, title: '完整历史', items: [{ request_id: 'old' }], next_cursor: null },
    ]
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(pages[0]), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(pages[1]), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    const history = await getConversationHistory('real', 'conv-1')

    expect(history.items.map((item) => item.request_id)).toEqual(['new', 'old'])
    expect(String(fetchMock.mock.calls[1][0])).toContain('cursor=older')
  })

  it('passes an AbortSignal through every history page request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ runtime_mode: 'real', conversation_id: 'conv-1', archived_at: null, items: [], next_cursor: null }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()
    await getConversationHistory('real', 'conv-1', controller.signal)
    expect((fetchMock.mock.calls[0][1] as RequestInit).signal).toBe(controller.signal)
  })

  it('uses the existing conversation namespace for rename, archive, and delete', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify({ title: '新标题' }), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    ))
    vi.stubGlobal('fetch', fetchMock)

    await renameConversation('real', 'conv-1', '新标题')
    await archiveConversation('real', 'conv-1')
    await restoreConversation('real', 'conv-1')
    await deleteConversation('real', 'conv-1')

    expect(fetchMock.mock.calls.map((call) => (call[1] as RequestInit).method)).toEqual(['PATCH', 'POST', 'POST', 'DELETE'])
    expect(fetchMock.mock.calls.every((call) => String(call[0]).includes('runtime_mode=real'))).toBe(true)
    expect(String(fetchMock.mock.calls[3][0])).toContain('/api/v1/conversations/conv-1?')
  })

  it('deletes one report through the resource API without a conversation mutation', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ report_id: 'rpt-1', source_mode: 'real', conversation_id: 'conv-1', request_id: 'req-1', deleted: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    await deleteReport('rpt-1')
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/reports/rpt-1')
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe('DELETE')
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('/conversations/')
  })

  it('renames one report through presentation-only resource metadata', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          report_id: 'rpt-1',
          display_title: '区域销售报告',
          availability_status: 'available',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    await renameReport('rpt-1', '区域销售报告')
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/reports/rpt-1')
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe('PATCH')
    expect(JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body))).toEqual({
      display_title: '区域销售报告',
    })
  })
})
