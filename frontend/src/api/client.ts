import { tr } from '../i18n'
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
  FailureInfo,
  AuthSession,
  AuthState,
} from '../types'
import { publicFailureMessage } from '../failure'
import type { CloudDenialReason } from '../failure'
import type { CloudCatalog, CloudCatalogPage, CloudWorkspaceStatus } from '../cloudTypes'

export function projectPresentation(requestId:string,locale:string,mode:RuntimeMode,cloud:boolean,csrf:string,generation:number,signal?:AbortSignal) {
  return requestJson<{answer:string;presentation:import('../types').PresentationEnvelope;factual_hash:string}>(
    `${cloud?'/api/v1/cloud/presentations/':'/api/v1/presentations/'}${encodeURIComponent(requestId)}`,{
      method:'POST',signal,headers:cloud?{'X-CSRF-Token':csrf}:{},
      body:JSON.stringify(cloud?{locale,expected_generation:generation}:{locale,runtime_mode:mode}),
    })
}

interface ErrorPayload {
  detail?: unknown
  error_type?: unknown
  failure?: unknown
  denial_reason?: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly errorType?: string
  readonly failure?: FailureInfo
  readonly authState?: AuthState
  readonly denialReason?: CloudDenialReason

  constructor(
    message: string,
    status: number,
    errorType?: string,
    failure?: FailureInfo,
    authState?: AuthState,
    denialReason?: CloudDenialReason,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.errorType = errorType
    this.failure = failure
    this.authState = authState
    this.denialReason = denialReason
  }
}

function url(path: string): string {
  if (path.startsWith('/auth/') || path.startsWith('/api/v1/cloud/')) return path // BFF always same-origin.
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
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(tr('errors:cannotConnectToPowerbiagentCheckYourNetworkAndTry'), 0)
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
    const failure = parseFailure(payload.failure) || parseFailure(nested?.failure)
    const reason = payload.denial_reason || nested?.denial_reason
    throw new ApiError(
      failure
        ? publicFailureMessage(failure)
        : friendlyHttpError(response.status, errorType),
      response.status,
      errorType,
      failure,
      AUTH_STATES.has(String((payload as {state?: unknown}).state))
        ? (payload as {state: AuthState}).state : undefined,
      reason==='test_scope_missing' || reason==='cloud_execution_blocked' || reason==='cloud_disclosure_blocked' || reason==='cloud_persistence_blocked' ? reason : undefined,
    )
  }

  return (await response.json()) as T
}

function parseFailure(value: unknown): FailureInfo | undefined {
  if (!value || typeof value !== 'object') return undefined
  const candidate = value as Partial<FailureInfo>
  if (
    !PUBLIC_FAILURE_CODES.has(String(candidate.code)) ||
    !FAILURE_STAGES.has(String(candidate.stage)) ||
    typeof candidate.retryable !== 'boolean' ||
    !FAILURE_RECOVERY_ACTIONS.has(String(candidate.recovery_action))
  ) return undefined
  return candidate as FailureInfo
}

const PUBLIC_FAILURE_CODES = new Set([
  'PERSISTENCE_UNAVAILABLE',
  'AUTH_REQUIRED', 'AUTH_EXPIRED', 'AUTH_CONSENT_REQUIRED', 'AUTH_FORBIDDEN',
  'RESOURCE_NOT_ACCESSIBLE', 'MODEL_RESOLUTION_FAILED', 'SCHEMA_UNAVAILABLE',
  'QUERY_REJECTED', 'QUERY_TIMEOUT', 'RATE_LIMITED', 'UPSTREAM_UNAVAILABLE', 'CONTRACT_DRIFT',
  'REPORT_TEMPLATE_INCOMPATIBLE', 'REPORT_TEMPLATE_UNAVAILABLE',
  'REPORT_DATA_UNAVAILABLE', 'REPORT_EXECUTION_FAILED',
  'REPORT_RENDER_FAILED', 'POWERBI_CONNECTION_LOST',
  'SEMANTIC_MODEL_STALE', 'LLM_SERVICE_UNAVAILABLE', 'REQUEST_TIMEOUT',
  'VALIDATION_FAILED', 'INTERNAL_FAILURE',
])

const FAILURE_STAGES = new Set([
  'auth',
  'report_scope', 'report_plan', 'report_query_validation',
  'report_dax_execution', 'sales_report_data_assembly', 'sales_report_spec',
  'report_render_store', 'memory_commit', 'understanding', 'grounding',
  'answer_generation', 'tool_execution', 'provider', 'internal',
])

const FAILURE_RECOVERY_ACTIONS = new Set([
  'login', 'relogin', 'consent_or_contact_admin', 'switch_account_or_contact_admin',
  'retry', 'refresh_semantic_models', 'reselect_semantic_model',
  'reselect_report_template', 'edit_request', 'none',
])

const AUTH_STATES = new Set(['SIGNED_OUT', 'AUTHENTICATING', 'SESSION_ESTABLISHING',
  'SIGNED_IN', 'AUTH_ERROR', 'CONSENT_REQUIRED', 'SESSION_EXPIRED'])

export async function readAuthSession(signal?: AbortSignal): Promise<AuthSession> {
  try {
    const dto = await requestJson<AuthSession>('/auth/session', {signal})
    if (!['LOCAL_DEV', 'ENTRA_BFF'].includes(dto.identity_mode)) throw new Error('Invalid identity mode')
    if (dto.identity_mode === 'ENTRA_BFF' && (!dto.authenticated || !dto.csrf_token || !dto.expires_in)) {
      throw new Error('Invalid session')
    }
    return {identity_mode:dto.identity_mode, authenticated:dto.authenticated,
      display_name:dto.display_name, preferred_username:dto.preferred_username,
      state:dto.identity_mode === 'LOCAL_DEV' ? 'LOCAL_DEV' : 'SIGNED_IN',
      csrf_token:dto.csrf_token, expires_in:dto.expires_in}
  } catch (error) {
    if (error instanceof ApiError && (error.status===401 || ['AUTH_REQUIRED','AUTH_EXPIRED'].includes(error.failure?.code || ''))) {
      return {identity_mode:'ENTRA_BFF', authenticated:false, display_name:null,
        preferred_username:null, csrf_token:null, expires_in:0,
        state:error.authState || 'SIGNED_OUT'}
    }
    throw error
  }
}

export async function logoutAuthSession(csrf: string): Promise<void> {
  try {
    await requestJson('/auth/logout', {method:'POST', headers:{'X-CSRF-Token':csrf}})
  } catch (error) {
    if (error instanceof ApiError && error.status === 401 &&
      ['AUTH_REQUIRED', 'AUTH_EXPIRED'].includes(error.failure?.code || '')) return
    throw error
  }
}

function friendlyHttpError(status: number, errorType?: string): string {
  if (errorType === 'llm_profile_unknown' || errorType === 'llm_profile_unavailable') {
    return tr('errors:theSelectedAiModelIsUnavailableRefreshAndSelect')
  }
  if (errorType === 'conversation_history_requires_sqlite') {
    return tr('errors:conversationStorageIsDisabledHistoryIsUnavailable')
  }
  if (errorType === 'semantic_model_discovery_unavailable') {
    return tr('errors:cannotLoadPowerBiDataModelsRightNow')
  }
  if (status === 404) return tr('errors:thisConversationOrReportNoLongerExists')
  if (status === 409) return tr('errors:thisRequestConflictsWithAnExistingRequestSendIt')
  if (status === 422) return tr('errors:theRequestIsIncompleteCheckItAndTryAgain')
  if (status === 429) return tr('errors:tooManyRequestsTryAgainLater')
  if (status === 502 || status === 503 || status === 504) {
    return tr('errors:theAnalysisServiceIsUnavailableTryAgainLater')
  }
  return tr('errors:somethingWentWrongWhileProcessingYourRequestTryAgain')
}

export async function discoverSemanticModels(): Promise<SemanticModelCatalog> {
  return requestJson<SemanticModelCatalog>('/api/v1/semantic-models')
}

export async function discoverReportTemplates(
  semanticModelKey: string,
): Promise<ReportTemplateCatalog> {
  const query = queryString({ semantic_model_key: semanticModelKey })
  return requestJson<ReportTemplateCatalog>(`/api/v1/report-templates?${query}`)
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

export const readCloudCatalog = (signal?: AbortSignal) =>
  requestJson<CloudCatalog>('/api/v1/cloud/catalog', { signal })
export const readCloudWorkspaces = (query = '', cursor?: string, signal?: AbortSignal) =>
  requestJson<CloudCatalogPage>('/api/v1/cloud/catalog/workspaces?' + queryString({query, cursor}), {signal})
export const readCloudResources = (workspaceKey: string, kind: 'SemanticModel' | 'Report', query = '', cursor?: string, signal?: AbortSignal) =>
  requestJson<CloudCatalogPage>('/api/v1/cloud/catalog/resources?' + queryString({workspace_key:workspaceKey, kind, query, cursor}), {signal})
export const readCloudStatus = (signal?: AbortSignal) =>
  requestJson<CloudWorkspaceStatus>('/api/v1/cloud/status', { signal })
export const selectCloudModel = (key: string, csrf: string, expectedGeneration: number, signal?: AbortSignal) =>
  requestJson<CloudWorkspaceStatus>('/api/v1/cloud/selection', {
    method: 'POST', body: JSON.stringify({ key, expected_generation: expectedGeneration }), headers: { 'X-CSRF-Token': csrf }, signal,
  })
export const openCloudResourceLink = (url: string, csrf: string, expectedGeneration: number, signal?: AbortSignal) =>
  requestJson<CloudWorkspaceStatus>('/api/v1/cloud/selection/link', {
    method:'POST',body:JSON.stringify({url,expected_generation:expectedGeneration}),headers:{'X-CSRF-Token':csrf},signal,
  })
export const readCloudProfiles = (signal?: AbortSignal) =>
  requestJson<LLMProfileCatalog>('/api/v1/cloud/llm-profiles', { signal })
export const readCloudTemplates = (signal?: AbortSignal) =>
  requestJson<ReportTemplateCatalog>('/api/v1/cloud/report-templates', { signal })

export const sendCloudChat = (body: {
  message: string; request_id: string; expected_generation: number
  llm_profile_key?: string; report_template_key?: string
}, csrf: string, signal?: AbortSignal) => requestJson<ChatResponse>('/api/v1/cloud/chat', {
  method:'POST',body:JSON.stringify(body),headers:{'X-CSRF-Token':csrf},signal,
})
export const newCloudChat = (expectedGeneration: number, csrf: string, signal?: AbortSignal) =>
  requestJson<CloudWorkspaceStatus>('/api/v1/cloud/new-chat', {
    method:'POST',body:JSON.stringify({expected_generation:expectedGeneration}),headers:{'X-CSRF-Token':csrf},signal,
  })
export const restoreCloudChat = (conversationId: string, expectedGeneration: number, csrf: string, signal?: AbortSignal) =>
  requestJson<CloudWorkspaceStatus>('/api/v1/cloud/restore', {
    method:'POST',body:JSON.stringify({conversation_id:conversationId,expected_generation:expectedGeneration}),
    headers:{'X-CSRF-Token':csrf},signal,
  })
export const readCloudHistory = (signal?: AbortSignal) =>
  requestJson<ConversationListPage>('/api/v1/cloud/history', {signal})
export const readCloudReports = (signal?: AbortSignal) =>
  requestJson<ReportResourcePage>('/api/v1/cloud/reports', {signal})
export const listCloudConversations = (status: 'active' | 'archived', limit=20, cursor?: string, q?: string, signal?: AbortSignal) =>
  requestJson<ConversationListPage>(`/api/v1/cloud/history?${queryString({status,limit,cursor,q})}`,{signal})
export const listCloudReports = (status: ReportResourceStatus, limit=20, cursor?: string, signal?: AbortSignal) =>
  requestJson<ReportResourcePage>(`/api/v1/cloud/reports?${queryString({status,limit,cursor})}`,{signal})
export type CloudResourceAction = 'rename' | 'archive' | 'unarchive' | 'delete'
export const mutateCloudResource = (kind: 'history' | 'reports', id: string, action: CloudResourceAction,
  expectedGeneration: number, csrf: string, title?: string, signal?: AbortSignal) =>
  requestJson<{workspace_status: CloudWorkspaceStatus}>(`/api/v1/cloud/${kind}/${encodeURIComponent(id)}${action==='delete'?'':'/'+action}`,{
    method:action==='delete'?'DELETE':'POST',body:JSON.stringify({expected_generation:expectedGeneration,title}),
    headers:{'X-CSRF-Token':csrf},signal,
  })
export async function readCloudConversation(id: string, signal?: AbortSignal): Promise<ConversationHistoryPage> {
  const items: ConversationHistoryPage['items']=[]
  let cursor: string | undefined
  let first: ConversationHistoryPage | undefined
  const seen=new Set<string>()
  do {
    const query=queryString({limit:50,cursor})
    const page=await requestJson<ConversationHistoryPage>(`/api/v1/cloud/history/${encodeURIComponent(id)}?${query}`,{signal})
    if (page.conversation_id!==id) throw new ApiError(tr('errors:historyIsUnavailableTryAgain'),503)
    first ||= page
    items.push(...page.items)
    cursor=page.next_cursor || undefined
    if (cursor && seen.has(cursor)) throw new ApiError(tr('errors:historyIsUnavailableTryAgain'),503)
    if (cursor) seen.add(cursor)
  } while (cursor)
  return {...first!,items,next_cursor:null}
}
