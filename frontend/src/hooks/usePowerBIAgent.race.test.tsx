import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  ChatRequest,
  ChatResponse,
  ConversationHistoryPage,
  ConversationSummary,
  RuntimeMode,
} from '../types'
import { compareConversationRecency, usePowerBIAgent } from './usePowerBIAgent'

const api = vi.hoisted(() => {
  class ApiError extends Error {
    readonly status: number
    readonly errorType?: string
    readonly failure?: { code: string }

    constructor(
      message: string,
      status: number,
      errorType?: string,
      failure?: { code: string },
    ) {
      super(message)
      this.status = status
      this.errorType = errorType
      this.failure = failure
    }
  }

  return {
    ApiError,
    archiveConversation: vi.fn(),
    deleteConversation: vi.fn(),
    deleteReport: vi.fn(),
    discoverReportTemplates: vi.fn(),
    discoverLLMProfiles: vi.fn(),
    discoverSemanticModels: vi.fn(),
    getConversationHistory: vi.fn(),
    listArchivedConversations: vi.fn(),
    listRecentConversations: vi.fn(),
    listRecentReports: vi.fn(),
    renameConversation: vi.fn(),
    renameReport: vi.fn(),
    recordFailedConversation: vi.fn(),
    restoreConversation: vi.fn(),
    searchConversations: vi.fn(),
    sendChat: vi.fn(),
  }
})

vi.mock('../api/client', () => api)

function summary(conversationId: string): ConversationSummary {
  return {
    runtime_mode: 'real',
    conversation_id: conversationId,
    created_at: '2026-08-24T10:00:00',
    updated_at: '2026-08-24T10:00:00',
    archived_at: null,
    title: conversationId,
    latest_request_id: null,
    latest_terminal_state: null,
    latest_response_type: null,
    latest_analysis_goal: null,
  }
}

it('sorts conversation resource truth by updated, created, then stable id descending', () => {
  const rows = [
    { ...summary('conv-a'), created_at: '2026-08-24T10:00:01', updated_at: '2026-08-24T10:01:00' },
    { ...summary('conv-b'), created_at: '2026-08-24T10:00:01', updated_at: '2026-08-24T10:01:00' },
    { ...summary('conv-z'), created_at: '2026-08-24T10:00:00', updated_at: '2026-08-24T10:01:00' },
    { ...summary('conv-c'), created_at: '2026-08-24T10:03:00', updated_at: '2026-08-24T10:00:00' },
  ]
  expect(rows.sort(compareConversationRecency).map((item) => item.conversation_id)).toEqual([
    'conv-b', 'conv-a', 'conv-z', 'conv-c',
  ])
})

function history(
  conversationId: string,
  answer: string,
  withReport = false,
): ConversationHistoryPage {
  const report = withReport
    ? {
        report_id: 'rpt-a',
        template_key: 'sales_report',
        contract_version: '1.0',
        view_reference: '/api/reports/rpt-a',
        download_reference: '/api/reports/rpt-a/download',
        content_type: 'text/html; charset=utf-8',
        content_hash: 'a'.repeat(64),
      }
    : null
  return {
    runtime_mode: 'real',
    conversation_id: conversationId,
    archived_at: null,
    title: conversationId,
    next_cursor: null,
    items: [
      {
        request_id: `req-${conversationId}`,
        created_at: '2026-08-24T10:00:00',
        terminal_state: 'completed',
        response_type: withReport ? 'report' : 'answer',
        intent: withReport ? 'report_generation' : 'data_question',
        user_message: conversationId,
        answer: withReport ? null : answer,
        report,
        clarification_question: null,
        unsupported_reason: null,
        error_type: null,
      },
    ],
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

function response(body: ChatRequest, answer: string): ChatResponse {
  return {
    request_id: body.request_id,
    conversation_id: body.conversation_id!,
    terminal_state: 'completed',
    intent: 'data_question',
    response_type: 'answer',
    answer,
    report: null,
    clarification_question: null,
    unsupported_reason: null,
    error_type: null,
    source_mode: 'real',
    idempotent_replay: false,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  api.discoverSemanticModels.mockResolvedValue({
    runtime_mode: 'real' satisfies RuntimeMode,
    items: [{
      key: 'local:model',
      display_name: 'Rich',
      source: 'local_desktop',
      type: 'semantic_model',
      available: true,
      connected: true,
      agent_compatible: true,
      selectable: true,
      compatibility_status: 'compatible',
    }],
    error_type: null,
  })
  api.discoverReportTemplates.mockResolvedValue({
    items: [{
      template_key: 'sales_report',
      display_name: '简易模板',
      description: '适合快速查看关键指标、趋势与分类明细',
      availability: 'available',
      compatibility_status: 'compatible',
      selectable: true,
      available_section_count: 9,
      total_section_count: 9,
    }],
  })
  api.discoverLLMProfiles.mockResolvedValue({
    items: [
      {
        profile_key: 'deepseek',
        display_name: 'DeepSeek',
        provider_protocol: 'openai_chat_completions',
        model: 'deepseek-chat',
        available: true,
        default: true,
        unavailable_reason: null,
      },
      {
        profile_key: 'kimi-k2.6',
        display_name: 'Kimi K2.6',
        provider_protocol: 'openai_chat_completions',
        model: 'azure/Kimi-K2.6',
        available: true,
        default: false,
        unavailable_reason: null,
      },
    ],
  })
  api.listRecentConversations.mockResolvedValue({
    runtime_mode: 'real', items: [], next_cursor: null, total_count: 0,
  })
  api.listArchivedConversations.mockResolvedValue({
    runtime_mode: 'real', items: [], next_cursor: null, total_count: 0,
  })
  api.listRecentReports.mockResolvedValue([])
  api.archiveConversation.mockResolvedValue(undefined)
  api.deleteConversation.mockResolvedValue(undefined)
  api.deleteReport.mockResolvedValue({ deleted: true })
  api.renameReport.mockImplementation(
    async (_reportId: string, displayTitle: string) => ({
      report_id: 'rpt-a',
      display_title: displayTitle,
      availability_status: 'available',
    }),
  )
  api.recordFailedConversation.mockResolvedValue({
    runtime_mode: 'real',
    conversation_id: 'failed',
    resource_status: 'failed',
    last_error_type: 'client_request_failed',
    updated_at: '2026-08-24T10:05:00',
  })
})

it('persists a rejected chat as a manageable failed conversation resource', async () => {
  api.sendChat.mockRejectedValue(new Error('network failed'))
  const { result } = renderHook(() => usePowerBIAgent())
  await waitFor(() => expect(result.current.loadingSemanticModels).toBe(false))

  let conversationId = ''
  await act(async () => {
    conversationId = result.current.startNewChat()
    await result.current.submitMessage('will fail')
  })

  expect(api.recordFailedConversation).toHaveBeenCalledWith(
    'real',
    conversationId,
    expect.objectContaining({
      title: 'will fail',
      error_type: 'client_request_failed',
    }),
  )
  expect(result.current.recentConversations[0]).toMatchObject({
    conversation_id: conversationId,
    local_status: 'failed',
  })
})

describe('conversation history stale-response protection', () => {
  it('drops A when its slow history returns after B became active', async () => {
    const a = deferred<ConversationHistoryPage>()
    api.getConversationHistory.mockImplementation(
      (_mode: RuntimeMode, id: string) =>
        id === 'A' ? a.promise : Promise.resolve(history('B', 'B answer')),
    )
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingSemanticModels).toBe(false))

    let aOpen!: Promise<void>
    await act(async () => {
      aOpen = result.current.openConversation(summary('A'))
      await result.current.openConversation(summary('B'))
    })
    expect(result.current.activeConversationId).toBe('B')
    expect(result.current.messages.some((item) => item.role === 'assistant' && item.content === 'B answer')).toBe(true)

    await act(async () => {
      a.resolve(history('A', 'A answer', true))
      await aOpen
    })
    expect(result.current.activeConversationId).toBe('B')
    expect(result.current.messages.some((item) => item.role === 'assistant' && item.content === 'A answer')).toBe(false)
    expect(result.current.messages.some((item) => item.role === 'assistant' && item.report?.report_id === 'rpt-a')).toBe(false)
  })

  it('new chat aborts the old history and keeps the canvas empty', async () => {
    const a = deferred<ConversationHistoryPage>()
    let signal: AbortSignal | undefined
    api.getConversationHistory.mockImplementation(
      (_mode: RuntimeMode, _id: string, currentSignal: AbortSignal) => {
        signal = currentSignal
        return a.promise
      },
    )
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingSemanticModels).toBe(false))
    let opening!: Promise<void>
    act(() => {
      opening = result.current.openConversation(summary('A'))
      result.current.startNewChat()
    })
    expect(signal?.aborted).toBe(true)
    await act(async () => {
      a.resolve(history('A', 'A answer', true))
      await opening
    })
    expect(result.current.activeConversationId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    )
    expect(result.current.activeSession?.status).toBe('draft')
    expect(result.current.messages).toEqual([])
  })

  it.each(['archive', 'remove'] as const)(
    '%s A prevents its late report from appearing in B',
    async (action) => {
      const a = deferred<ConversationHistoryPage>()
      api.getConversationHistory.mockImplementation(
        (_mode: RuntimeMode, id: string) =>
          id === 'A' ? a.promise : Promise.resolve(history('B', 'B answer')),
      )
      const { result } = renderHook(() => usePowerBIAgent())
      await waitFor(() => expect(result.current.loadingSemanticModels).toBe(false))
      let aOpen!: Promise<void>
      await act(async () => {
        aOpen = result.current.openConversation(summary('A'))
        await result.current[action](summary('A'))
        await result.current.openConversation(summary('B'))
      })
      await act(async () => {
        a.resolve(history('A', 'A answer', true))
        await aOpen
      })
      expect(result.current.activeConversationId).toBe('B')
      expect(result.current.messages.some((item) => item.role === 'assistant' && item.report)).toBe(false)
    },
  )
})

describe('conversation-owned chat concurrency', () => {
  it('captures the selected profile per request across concurrent conversations', async () => {
    const pending = new Map<string, ReturnType<typeof deferred<ChatResponse>>>()
    api.sendChat.mockImplementation((body: ChatRequest) => {
      const task = deferred<ChatResponse>()
      pending.set(body.message, task)
      return task.promise
    })
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingLLMProfiles).toBe(false))

    let deepseekRequest!: Promise<void>
    let kimiRequest!: Promise<void>
    act(() => {
      result.current.startNewChat()
      deepseekRequest = result.current.submitMessage('DeepSeek request')
    })
    act(() => {
      result.current.setSelectedLLMProfile(result.current.llmProfileOptions[1])
      result.current.startNewChat()
      kimiRequest = result.current.submitMessage('Kimi request')
    })
    await waitFor(() => expect(api.sendChat).toHaveBeenCalledTimes(2))
    const deepseekBody = api.sendChat.mock.calls[0][0] as ChatRequest
    const kimiBody = api.sendChat.mock.calls[1][0] as ChatRequest
    expect(deepseekBody.llm_profile_key).toBe('deepseek')
    expect(kimiBody.llm_profile_key).toBe('kimi-k2.6')

    await act(async () => {
      pending.get('DeepSeek request')!.resolve(response(deepseekBody, 'deep result'))
      pending.get('Kimi request')!.resolve(response(kimiBody, 'kimi result'))
      await Promise.all([deepseekRequest, kimiRequest])
    })
  })

  it('uses a newly selected profile on the next turn without changing the prior request', async () => {
    api.sendChat.mockImplementation((body: ChatRequest) =>
      Promise.resolve(response(body, `${body.llm_profile_key} result`)),
    )
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingLLMProfiles).toBe(false))

    act(() => { result.current.startNewChat() })
    await act(async () => { await result.current.submitMessage('first turn') })
    act(() => {
      result.current.setSelectedLLMProfile(result.current.llmProfileOptions[1])
    })
    await act(async () => { await result.current.submitMessage('second turn') })

    expect((api.sendChat.mock.calls[0][0] as ChatRequest).llm_profile_key).toBe('deepseek')
    expect((api.sendChat.mock.calls[1][0] as ChatRequest).llm_profile_key).toBe('kimi-k2.6')
  })

  it('does not project A loading into a newly opened idle B', async () => {
    const pending = deferred<ChatResponse>()
    api.sendChat.mockImplementation(() => pending.promise)
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingSemanticModels).toBe(false))
    let aId = ''
    let aRequest!: Promise<void>
    let bId = ''
    act(() => {
      aId = result.current.startNewChat()
      aRequest = result.current.submitMessage('A pending')
      bId = result.current.startNewChat()
    })
    expect(result.current.sessions[aId].sending).toBe(true)
    expect(result.current.activeConversationId).toBe(bId)
    expect(result.current.sending).toBe(false)
    expect(result.current.loadingConversation).toBe(false)
    expect(result.current.messages).toEqual([])

    const body = api.sendChat.mock.calls[0][0] as ChatRequest
    await act(async () => {
      pending.resolve(response(body, 'A complete'))
      await aRequest
    })
    expect(result.current.activeConversationId).toBe(bId)
    expect(result.current.messages).toEqual([])
  })

  it('runs A/B/C concurrently and updates only the owning session', async () => {
    const pending = new Map<string, ReturnType<typeof deferred<ChatResponse>>>()
    api.sendChat.mockImplementation((body: ChatRequest) => {
      const task = deferred<ChatResponse>()
      pending.set(body.message, task)
      return task.promise
    })
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingSemanticModels).toBe(false))

    let aId = ''
    let bId = ''
    let cId = ''
    let aRequest!: Promise<void>
    let bRequest!: Promise<void>
    let cRequest!: Promise<void>
    act(() => {
      aId = result.current.startNewChat()
      aRequest = result.current.submitMessage('A question')
    })
    await waitFor(() => expect(result.current.sessions[aId]?.sending).toBe(true))
    expect(result.current.recentConversations[0]).toMatchObject({
      conversation_id: aId,
      local_status: 'processing',
    })

    act(() => {
      bId = result.current.startNewChat()
      bRequest = result.current.submitMessage('B question')
      cId = result.current.startNewChat()
      cRequest = result.current.submitMessage('C question')
    })
    await waitFor(() => expect(api.sendChat).toHaveBeenCalledTimes(3))
    expect(result.current.sessions[aId].sending).toBe(true)
    expect(result.current.sessions[bId].sending).toBe(true)
    expect(result.current.sessions[cId].sending).toBe(true)

    await act(async () => {
      await result.current.openConversation(
        result.current.recentConversations.find(
          (item) => item.conversation_id === bId,
        )!,
      )
    })
    expect(result.current.activeConversationId).toBe(bId)
    expect(result.current.sending).toBe(true)
    expect(result.current.messages.some((item) => item.role === 'user' && item.content === 'A question')).toBe(false)

    const aBody = api.sendChat.mock.calls.find(
      (call) => (call[0] as ChatRequest).message === 'A question',
    )![0] as ChatRequest
    await act(async () => {
      pending.get('A question')!.resolve(response(aBody, 'A answer'))
      await aRequest
    })
    expect(result.current.activeConversationId).toBe(bId)
    expect(result.current.sessions[aId].messages.some((item) => item.role === 'assistant' && item.content === 'A answer')).toBe(true)
    expect(result.current.sessions[bId].messages.some((item) => item.role === 'assistant' && item.content === 'A answer')).toBe(false)

    const bBody = api.sendChat.mock.calls.find(
      (call) => (call[0] as ChatRequest).message === 'B question',
    )![0] as ChatRequest
    const cBody = api.sendChat.mock.calls.find(
      (call) => (call[0] as ChatRequest).message === 'C question',
    )![0] as ChatRequest
    await act(async () => {
      pending.get('B question')!.resolve(response(bBody, 'B answer'))
      pending.get('C question')!.resolve(response(cBody, 'C answer'))
      await Promise.all([bRequest, cRequest])
    })
    expect(result.current.sessions[bId].messages.some((item) => item.role === 'assistant' && item.content === 'B answer')).toBe(true)
    expect(result.current.sessions[cId].messages.some((item) => item.role === 'assistant' && item.content === 'C answer')).toBe(true)
  })

  it('serializes a single conversation while another conversation can send', async () => {
    const pending = deferred<ChatResponse>()
    api.sendChat.mockImplementation((body: ChatRequest) =>
      body.message === 'first'
        ? pending.promise
        : Promise.resolve(response(body, 'other answer')),
    )
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingSemanticModels).toBe(false))

    let first!: Promise<void>
    let other!: Promise<void>
    act(() => {
      result.current.startNewChat()
      first = result.current.submitMessage('first')
      void result.current.submitMessage('blocked second')
      result.current.startNewChat()
      other = result.current.submitMessage('other')
    })
    await waitFor(() => expect(api.sendChat).toHaveBeenCalledTimes(2))
    await act(async () => { await other })
    const firstBody = api.sendChat.mock.calls[0][0] as ChatRequest
    await act(async () => {
      pending.resolve(response(firstBody, 'first answer'))
      await first
    })
  })
})

describe('report presentation synchronization', () => {
  it('distinguishes schema failure from a normal empty template catalog', async () => {
    api.discoverReportTemplates.mockResolvedValue({ items: [], reason_code: 'semantic_model_schema_unavailable' })
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingReportTemplates).toBe(false))
    expect(result.current.reportTemplateOptions).toEqual([])
    expect(result.current.selectedReportTemplate).toBeNull()
    expect(result.current.reportTemplateError).toBe('暂时无法获取当前数据模型的结构，请稍后重试。')
  })

  it('keeps the Logistics empty catalog after a late Sales response and allows Q&A', async () => {
    const sales = deferred<{ items: object[] }>()
    api.discoverSemanticModels.mockResolvedValue({
      runtime_mode: 'real', error_type: null,
      items: ['sales', 'logistics'].map((key) => ({
        key, display_name: key, source: 'local_desktop', type: 'semantic_model',
        available: true, connected: true, agent_compatible: true,
        selectable: true, compatibility_status: 'compatible',
      })),
    })
    api.discoverReportTemplates.mockImplementation((key: string) => key === 'sales'
      ? sales.promise
      : Promise.resolve({ items: [], reason_code: 'no_eligible_report_template' }))
    api.sendChat.mockImplementation((body: ChatRequest) => Promise.resolve(response(body, 'verified answer')))
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(api.discoverReportTemplates).toHaveBeenCalledWith('sales'))
    act(() => result.current.setSelectedSemanticModel(result.current.semanticModelOptions[1]))
    await waitFor(() => expect(result.current.loadingReportTemplates).toBe(false))
    expect(result.current.reportTemplateError).toBe('当前数据模型暂无适配的报表模板，但仍可正常进行数据问答。')
    await act(async () => { sales.resolve({ items: [{
      template_key: 'sales_report', display_name: '简易销售分析模板', description: '销售',
      availability: 'available', compatibility_status: 'compatible', selectable: true,
      available_section_count: 9, total_section_count: 9,
    }] }) })
    expect(result.current.selectedSemanticModel?.key).toBe('logistics')
    expect(result.current.reportTemplateOptions).toEqual([])
    expect(result.current.selectedReportTemplate).toBeNull()
    await act(async () => { await result.current.submitMessage('Total Shipments是多少？') })
    expect(api.sendChat.mock.lastCall?.[0]).toMatchObject({ semantic_model_key: 'logistics' })
    expect(api.sendChat.mock.lastCall?.[0].report_template_key).toBeUndefined()
  })

  it('finishes catalog loading without querying templates when no model is available', async () => {
    api.discoverSemanticModels.mockResolvedValue({
      runtime_mode: 'real', items: [], error_type: null,
    })
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingSemanticModels).toBe(false))
    expect(result.current.loadingReportTemplates).toBe(false)
    expect(result.current.reportTemplateOptions).toEqual([])
    expect(api.discoverReportTemplates).not.toHaveBeenCalled()
  })

  it('ignores an in-flight template response after model discovery loses the selection', async () => {
    const pending = deferred<{ items: [] }>()
    api.discoverReportTemplates.mockReturnValue(pending.promise)
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(api.discoverReportTemplates).toHaveBeenCalled())
    api.discoverSemanticModels.mockResolvedValue({
      runtime_mode: 'real', items: [], error_type: null,
    })
    await act(async () => { await result.current.refreshSemanticModels() })
    await act(async () => { pending.resolve({ items: [] }) })
    expect(result.current.selectedSemanticModel).toBeNull()
    expect(result.current.loadingReportTemplates).toBe(false)
    expect(result.current.reportTemplateOptions).toEqual([])
    expect(result.current.reportTemplateError).toBeNull()
  })

  it('refetches compatibility and clears a template invalidated by a model switch', async () => {
    api.discoverSemanticModels.mockResolvedValue({
      runtime_mode: 'real',
      items: [
        {
          key: 'local:model', display_name: 'Rich', source: 'local_desktop',
          type: 'semantic_model', available: true, connected: true,
          agent_compatible: true, selectable: true, compatibility_status: 'compatible',
        },
        {
          key: 'local:other', display_name: 'Other', source: 'local_desktop',
          type: 'semantic_model', available: true, connected: true,
          agent_compatible: true, selectable: true, compatibility_status: 'compatible',
        },
      ],
      error_type: null,
    })
    api.discoverReportTemplates.mockImplementation(async (modelKey: string) => ({
      items: [{
        template_key: 'sales_report', display_name: '简易模板', description: '报表模板',
        availability: 'available',
        compatibility_status: modelKey === 'local:model' ? 'partial' : 'incompatible',
        selectable: modelKey === 'local:model',
        available_section_count: modelKey === 'local:model' ? 4 : 0,
        total_section_count: 9,
      }],
    }))
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingReportTemplates).toBe(false))
    act(() => {
      result.current.setSelectedReportTemplate(result.current.reportTemplateOptions[0])
      result.current.setSelectedSemanticModel(result.current.semanticModelOptions[1])
    })

    await waitFor(() => expect(result.current.loadingReportTemplates).toBe(false))
    expect(api.discoverReportTemplates).toHaveBeenLastCalledWith('local:other')
    expect(result.current.selectedReportTemplate).toBeNull()
    expect(result.current.reportTemplateError).toBe(
      '当前报表模板不适用于新选择的数据模型，请重新选择。',
    )
    expect(result.current.reportTemplateOptions[0]).toMatchObject({
      compatible: false,
      selectable: false,
      compatibilityStatus: 'incompatible',
    })
  })

  it('keeps the exact template through ordinary and failed turns until a report completes', async () => {
    api.sendChat.mockImplementation((body: ChatRequest) => {
      if (body.message === 'failed report') {
        return Promise.resolve({
          ...response(body, ''),
          terminal_state: 'response_failed',
          intent: 'report_generation',
          response_type: 'error',
          error_type: 'report_pipeline_failed',
        })
      }
      if (body.message === 'completed report') {
        return Promise.resolve({
          ...response(body, '报表已生成'),
          intent: 'report_generation',
          response_type: 'report',
          report: {
            report_id: 'rpt-a',
            template_key: 'sales_report',
            contract_version: '1.0',
            view_reference: '/api/reports/rpt-a',
            download_reference: '/api/reports/rpt-a/download',
            content_type: 'text/html; charset=utf-8',
            content_hash: 'a'.repeat(64),
          },
        })
      }
      return Promise.resolve(response(body, '普通回答'))
    })
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingReportTemplates).toBe(false))
    act(() => {
      result.current.startNewChat()
      result.current.setSelectedReportTemplate(result.current.reportTemplateOptions[0])
    })
    await act(async () => { await result.current.submitMessage('ordinary question') })
    expect(result.current.selectedReportTemplate?.key).toBe('sales_report')
    await act(async () => { await result.current.submitMessage('failed report') })
    expect(result.current.selectedReportTemplate?.key).toBe('sales_report')
    await act(async () => { await result.current.submitMessage('completed report') })
    expect(result.current.selectedReportTemplate).toBeNull()
    expect(api.sendChat.mock.calls.map(([body]) => body.report_template_key)).toEqual([
      'sales_report', 'sales_report', 'sales_report',
    ])
  })

  it('uses typed HTTP template failures to clear only the invalid template', async () => {
    api.sendChat.mockRejectedValue(new api.ApiError(
      '当前数据模型不支持这个报表模板，请选择其他模板或数据模型。',
      409,
      'opaque_report_error',
      { code: 'REPORT_TEMPLATE_INCOMPATIBLE' },
    ))
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingReportTemplates).toBe(false))
    act(() => {
      result.current.startNewChat()
      result.current.setSelectedReportTemplate(result.current.reportTemplateOptions[0])
    })

    await act(async () => { await result.current.submitMessage('生成销售报表') })

    expect(result.current.selectedReportTemplate).toBeNull()
    expect(result.current.selectedSemanticModel?.key).toBe('local:model')
    expect(result.current.reportTemplateError).toBe(
      '当前报表模板不适用于新选择的数据模型，请重新选择。',
    )
  })

  it('keeps rename and delete tombstone synchronized with the active report card', async () => {
    api.getConversationHistory.mockResolvedValue(history('A', '', true))
    const { result } = renderHook(() => usePowerBIAgent())
    await waitFor(() => expect(result.current.loadingSemanticModels).toBe(false))
    await act(async () => {
      await result.current.openConversation(summary('A'))
    })
    const report = {
      report_id: 'rpt-a',
      template_key: 'sales_report',
      contract_version: '1.0',
      view_reference: '/api/reports/rpt-a',
      download_reference: '/api/reports/rpt-a/download',
      content_type: 'text/html; charset=utf-8',
      content_hash: 'a'.repeat(64),
      display_title: '销售分析报告',
      availability_status: 'available' as const,
      source_mode: 'real' as const,
      conversation_id: 'A',
      request_id: 'req-A',
      semantic_model_key: 'model',
      generated_at: '2026-08-24T10:00:00',
      stored_at: '2026-08-24T10:00:00',
      archived_at: null,
    }
    await act(async () => {
      await result.current.renameReport(report, '区域销售报告')
    })
    expect(result.current.messages.find((item) => item.role === 'assistant')?.report?.display_title).toBe('区域销售报告')

    await act(async () => {
      await result.current.removeReport({
        ...report,
        display_title: '区域销售报告',
      })
    })
    expect(result.current.messages.find((item) => item.role === 'assistant')?.report).toMatchObject({
      display_title: '区域销售报告',
      availability_status: 'deleted',
      view_reference: '',
      download_reference: '',
    })
  })
})
