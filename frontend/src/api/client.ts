import { apiBaseUrl } from '../config'
import type {
  ChatRequest,
  ChatResponse,
  ConversationFailureResult,
  ConversationHistoryPage,
  ConversationListPage,
  ConversationReportItem,
  ConversationReportPage,
  ReportArchiveResult,
  ReportDeleteResult,
  ReportRenameResult,
  ReportResourcePage,
  ReportResourceStatus,
  ReportRestoreResult,
  RuntimeMode,
  SemanticModelCatalog,
  ReportTemplateCatalog,
  LLMProfileCatalog,
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
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
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
    const detailType =
      typeof payload.detail === 'string' && payload.detail.includes('_')
        ? payload.detail
        : undefined
    const effectiveErrorType = errorType || detailType
    throw new ApiError(
      friendlyHttpError(response.status, effectiveErrorType),
      response.status,
      effectiveErrorType,
    )
  }

  return (await response.json()) as T
}

function friendlyHttpError(status: number, errorType?: string): string {
  if (errorType === 'llm_profile_unknown' || errorType === 'llm_profile_unavailable') {
    return '当前选择的 AI 模型已失效，请刷新后重新选择。'
  }
  if (errorType === 'conversation_history_requires_sqlite') {
    return '会话持久化未启用，历史记录暂不可用。'
  }
  if (errorType === 'semantic_model_discovery_unavailable') {
    return '暂时无法获取 Power BI 数据模型。'
  }
  if (status === 404) return '请求的对话或报表已不存在。'
  if (status === 409) return '该请求与已有请求冲突，请重新发送。'
  if (status === 422) return '请求内容不完整，请检查后重试。'
  if (status === 429) return '请求过于频繁，请稍后再试。'
  if (status === 502 || status === 503 || status === 504) {
    return '分析服务暂时不可用，请稍后重试。'
  }
  return '处理请求时出现问题，请稍后重试。'
}

export async function discoverSemanticModels(): Promise<SemanticModelCatalog> {
  return requestJson<SemanticModelCatalog>('/api/v1/semantic-models')
}

export async function discoverReportTemplates(): Promise<ReportTemplateCatalog> {
  return requestJson<ReportTemplateCatalog>('/api/v1/report-templates')
}

export async function discoverLLMProfiles(): Promise<LLMProfileCatalog> {
  return requestJson<LLMProfileCatalog>('/api/v1/llm-profiles')
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
  cursor?: string,
): Promise<ConversationListPage> {
  const query = queryString({ runtime_mode: runtimeMode, limit, cursor })
  return requestJson<ConversationListPage>(`/api/v1/conversations?${query}`)
}

export async function listArchivedConversations(
  runtimeMode: RuntimeMode,
  limit = 12,
  cursor?: string,
): Promise<ConversationListPage> {
  const query = queryString({ runtime_mode: runtimeMode, limit, cursor })
  return requestJson<ConversationListPage>(
    `/api/v1/conversations/archived?${query}`,
  )
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
  signal?: AbortSignal,
): Promise<ConversationHistoryPage> {
  const items: ConversationHistoryPage['items'] = []
  let cursor: string | undefined
  let firstPage: ConversationHistoryPage | undefined
  do {
    const query = queryString({ runtime_mode: runtimeMode, limit: 50, cursor })
    const page = await requestJson<ConversationHistoryPage>(
      `/api/v1/conversations/${encodeURIComponent(conversationId)}/history?${query}`,
      { signal },
    )
    firstPage ||= page
    items.push(...page.items)
    cursor = page.next_cursor || undefined
  } while (cursor && items.length < 500)
  return { ...firstPage!, items, next_cursor: cursor || null }
}

export async function renameConversation(
  runtimeMode: RuntimeMode,
  conversationId: string,
  title: string,
): Promise<{ title: string; updated_at: string }> {
  const query = queryString({ runtime_mode: runtimeMode })
  return requestJson<{ title: string; updated_at: string }>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}?${query}`,
    { method: 'PATCH', body: JSON.stringify({ title }) },
  )
}

export async function recordFailedConversation(
  runtimeMode: RuntimeMode,
  conversationId: string,
  failure: { title: string; error_type: string },
): Promise<ConversationFailureResult> {
  const query = queryString({ runtime_mode: runtimeMode })
  return requestJson<ConversationFailureResult>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}/failure?${query}`,
    { method: 'POST', body: JSON.stringify(failure) },
  )
}

export async function archiveConversation(
  runtimeMode: RuntimeMode,
  conversationId: string,
): Promise<void> {
  const query = queryString({ runtime_mode: runtimeMode })
  await requestJson(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}/archive?${query}`,
    { method: 'POST' },
  )
}

export async function restoreConversation(
  runtimeMode: RuntimeMode,
  conversationId: string,
): Promise<void> {
  const query = queryString({ runtime_mode: runtimeMode })
  await requestJson(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}/restore?${query}`,
    { method: 'POST' },
  )
}

export async function deleteConversation(
  runtimeMode: RuntimeMode,
  conversationId: string,
): Promise<void> {
  const query = queryString({ runtime_mode: runtimeMode })
  await requestJson(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}?${query}`,
    { method: 'DELETE' },
  )
}

export async function deleteReport(reportId: string): Promise<ReportDeleteResult> {
  return requestJson<ReportDeleteResult>(
    `/api/reports/${encodeURIComponent(reportId)}`,
    { method: 'DELETE' },
  )
}

export async function renameReport(
  reportId: string,
  displayTitle: string,
): Promise<ReportRenameResult> {
  return requestJson<ReportRenameResult>(
    `/api/reports/${encodeURIComponent(reportId)}`,
    { method: 'PATCH', body: JSON.stringify({ display_title: displayTitle }) },
  )
}

export async function archiveReport(
  sourceMode: RuntimeMode,
  reportId: string,
): Promise<ReportArchiveResult> {
  const query = queryString({ source_mode: sourceMode })
  return requestJson<ReportArchiveResult>(
    `/api/reports/${encodeURIComponent(reportId)}/archive?${query}`,
    { method: 'POST' },
  )
}

export async function restoreReport(
  sourceMode: RuntimeMode,
  reportId: string,
): Promise<ReportRestoreResult> {
  const query = queryString({ source_mode: sourceMode })
  return requestJson<ReportRestoreResult>(
    `/api/reports/${encodeURIComponent(reportId)}/restore?${query}`,
    { method: 'POST' },
  )
}

export async function listManagedReports(
  sourceMode: RuntimeMode,
  status: ReportResourceStatus,
  limit = 20,
  cursor?: string,
): Promise<ReportResourcePage> {
  const query = queryString({ source_mode: sourceMode, status, limit, cursor })
  return requestJson<ReportResourcePage>(`/api/reports?${query}`)
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
  sourceMode: RuntimeMode,
): Promise<ConversationReportItem[]> {
  const page = await listManagedReports(sourceMode, 'active', 8)
  return page.items
}
