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

const api = vi.hoisted(() => ({
  archiveConversation: vi.fn(),
  deleteConversation: vi.fn(),
  deleteReport: vi.fn(),
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
}))

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
