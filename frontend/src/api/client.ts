import { apiBaseUrl } from '../config'
import type {
  ChatRequest,
  ChatResponse,
  ConversationHistoryPage,
  ConversationListPage,
  ConversationReportItem,
  ConversationReportPage,
  RuntimeMode,
} from '../types'

interface ErrorPayload {
  detail?: unknown
  error_type?: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly errorType?: string

  constructor(message: string, status: number, errorType?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.errorType = errorType
  }
}

function url(path: string): string {
  return `${apiBaseUrl}${path}`
}

function queryString(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) query.set(key, String(value))
  })
  return query.toString()
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url(path), {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError('无法连接到 PowerBIAgent 服务，请检查网络后重试。', 0)
  }

  if (!response.ok) {
    let payload: ErrorPayload = {}
    try {
      payload = (await response.json()) as ErrorPayload
    } catch {
      // Non-JSON server errors are intentionally not exposed to the UI.
    }
    const nested =
      typeof payload.detail === 'object' && payload.detail !== null
        ? (payload.detail as ErrorPayload)
        : undefined
    const errorType =
      typeof payload.error_type === 'string'
        ? payload.error_type
        : typeof nested?.error_type === 'string'
          ? nested.error_type
          : undefined
    throw new ApiError(friendlyHttpError(response.status), response.status, errorType)
  }

  return (await response.json()) as T
}

function friendlyHttpError(status: number): string {
  if (status === 404) return '请求的对话或报表已不存在。'
  if (status === 409) return '该请求与已有请求冲突，请重新发送。'
  if (status === 422) return '请求内容不完整，请检查后重试。'
  if (status === 429) return '请求过于频繁，请稍后再试。'
  if (status === 502 || status === 503 || status === 504) {
    return '分析服务暂时不可用，请稍后重试。'
  }
  return '处理请求时出现问题，请稍后重试。'
}

export async function sendChat(body: ChatRequest): Promise<ChatResponse> {
  return requestJson<ChatResponse>('/api/v1/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function listRecentConversations(
  runtimeMode: RuntimeMode,
  limit = 12,
): Promise<ConversationListPage> {
  const query = queryString({ runtime_mode: runtimeMode, limit })
  return requestJson<ConversationListPage>(`/api/v1/conversations?${query}`)
}

export async function searchConversations(
  runtimeMode: RuntimeMode,
  search: string,
  limit = 20,
): Promise<ConversationListPage> {
  const query = queryString({ runtime_mode: runtimeMode, q: search, limit })
  return requestJson<ConversationListPage>(`/api/v1/conversations/search?${query}`)
}

export async function getConversationHistory(
  runtimeMode: RuntimeMode,
  conversationId: string,
): Promise<ConversationHistoryPage> {
  const query = queryString({ runtime_mode: runtimeMode, limit: 50 })
  return requestJson<ConversationHistoryPage>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}/history?${query}`,
  )
}

export async function listConversationReports(
  sourceMode: RuntimeMode,
  conversationId: string,
  limit = 20,
): Promise<ConversationReportPage> {
  const query = queryString({ source_mode: sourceMode, limit })
  return requestJson<ConversationReportPage>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}/reports?${query}`,
  )
}

export async function listRecentReports(
  conversationIds: string[],
): Promise<ConversationReportItem[]> {
  const requests = conversationIds.flatMap((conversationId) =>
    (['real', 'mock'] as const).map((sourceMode) =>
      listConversationReports(sourceMode, conversationId, 6),
    ),
  )
  const pages = await Promise.allSettled(requests)
  const reports = pages.flatMap((result) =>
    result.status === 'fulfilled' ? result.value.items : [],
  )
  return reports
    .filter(
      (report, index, all) =>
        all.findIndex((candidate) => candidate.report_id === report.report_id) === index,
    )
    .sort((left, right) => right.stored_at.localeCompare(left.stored_at))
    .slice(0, 8)
}
