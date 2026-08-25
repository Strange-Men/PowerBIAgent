export type RuntimeMode = 'mock' | 'real'

export interface ChatRequest {
  message: string
  conversation_id?: string
  request_id: string
  semantic_model_key: string
  report_template_key?: string
}

export interface ReportResource {
  report_id: string
  template_key: string
  contract_version: string
  view_reference: string
  download_reference: string
  content_type: string
  content_hash: string
  display_title?: string
  availability_status?: 'available' | 'deleted'
}

export type PresentationCell = string | number | boolean | null

export interface PresentationDataset {
  result_id: string
  verified_fact_set_id: string
  semantic_model_key: string
  source_mode: RuntimeMode
  columns: string[]
  rows: PresentationCell[][]
  formatted_rows?: string[][]
  display_metadata?: Record<string, {
    canonical_name: string
    display_name: string
    object_identity: string
    object_type: string
    localization_source: string
    schema_identity: string
  }>
  row_count: number
  truncated: boolean
}

export type PresentationBlock =
  | { type: 'text'; content: string }
  | {
      type: 'metric'
      data_reference: string
      label: string
      value_field: string
      row_index: number
    }
  | { type: 'table'; data_reference: string; title: string }
  | {
      type: 'chart'
      data_reference: string
      visual_type: 'bar' | 'line'
      title: string
      x_field: string
      y_field: string
    }
  | { type: 'report_attachment'; report_id: string }

export interface PresentationEnvelope {
  version: 1
  datasets: PresentationDataset[]
  blocks: PresentationBlock[]
}

export interface ChatResponse {
  request_id: string
  conversation_id: string
  terminal_state: string
  intent: string
  response_type: string
  answer: string | null
  report: ReportResource | null
  presentation?: PresentationEnvelope | null
  clarification_question: string | null
  unsupported_reason: string | null
  error_type: string | null
  source_mode: RuntimeMode | ''
  llm_mode?: string
  powerbi_mode?: string
  memory_commit?: boolean
  idempotent_replay: boolean
}

export interface SemanticModelOption {
  key: string
  display_name: string
  source: 'mock' | 'local_desktop'
  type: 'semantic_model'
  available: boolean
  connected: boolean
  agent_compatible?: boolean
  selectable?: boolean
  schema_drift?: boolean
  compatibility_status?: 'compatible' | 'incompatible' | 'unavailable'
}

export interface SemanticModelCatalog {
  runtime_mode: RuntimeMode
  items: SemanticModelOption[]
  error_type: string | null
}

export interface ConversationSummary {
  runtime_mode: RuntimeMode
  conversation_id: string
  created_at: string
  updated_at: string
  archived_at: string | null
  title?: string | null
  latest_request_id: string | null
  latest_terminal_state: string | null
  latest_response_type: string | null
  latest_analysis_goal: string | null
  local_status?: 'processing' | 'failed' | 'ready'
  local_error?: string | null
}

export interface ConversationListPage {
  runtime_mode: RuntimeMode
  items: ConversationSummary[]
  next_cursor: string | null
  total_count: number
}

export interface ReportDeleteResult {
  report_id: string
  source_mode: RuntimeMode
  conversation_id: string | null
  request_id: string | null
  deleted: boolean
}

export interface ReportRenameResult {
  report_id: string
  display_title: string
  availability_status: 'available'
}

export interface ReportArchiveResult {
  report_id: string
  source_mode: RuntimeMode
  archived_at: string
}

export interface ReportRestoreResult {
  report_id: string
  source_mode: RuntimeMode
  restored: boolean
  updated_at: string
}

export interface ConversationHistoryItem {
  request_id: string
  created_at: string
  terminal_state: string
  response_type: string
  intent: string
  user_message?: string | null
  presentation?: PresentationEnvelope | null
  answer: string | null
  report: ReportResource | null
  clarification_question: string | null
  unsupported_reason: string | null
  error_type: string | null
}

export interface ConversationHistoryPage {
  runtime_mode: RuntimeMode
  conversation_id: string
  archived_at: string | null
  title?: string | null
  items: ConversationHistoryItem[]
  next_cursor: string | null
}

export interface ConversationReportItem extends ReportResource {
  source_mode: RuntimeMode
  conversation_id: string
  request_id: string | null
  semantic_model_key: string
  generated_at: string
  stored_at: string
  archived_at: string | null
}

export interface ConversationReportPage {
  source_mode: RuntimeMode
  conversation_id: string
  items: ConversationReportItem[]
  next_cursor: string | null
  total_count: number
}

export type ReportResourceStatus = 'active' | 'archived'

export interface ReportResourcePage {
  source_mode: RuntimeMode
  status: ReportResourceStatus
  items: ConversationReportItem[]
  next_cursor: string | null
  total_count: number
}

export type AssistantMessageKind =
  | 'answer'
  | 'clarification'
  | 'unsupported'
  | 'error'
  | 'empty'

export interface UserMessage {
  id: string
  role: 'user'
  content: string
}

export interface AssistantMessage {
  id: string
  role: 'assistant'
  kind: AssistantMessageKind
  content: string
  report?: ReportResource
  presentation?: PresentationEnvelope
  restored?: boolean
}

export type ConversationMessage = UserMessage | AssistantMessage

export type ConversationSessionStatus =
  | 'draft'
  | 'processing'
  | 'ready'
  | 'failed'

export interface ConversationSession {
  clientConversationId: string
  serverConversationId?: string
  title: string
  messages: ConversationMessage[]
  pendingRequests: string[]
  sending: boolean
  loadingHistory: boolean
  error: string | null
  status: ConversationSessionStatus
  restored: boolean
}

export interface BatchOperationResult {
  succeededIds: string[]
  failed: Array<{ id: string; reason: string }>
}

export interface CatalogOption {
  key: string
  label: string
  description: string
  compatible: boolean
  selectable?: boolean
  schemaDrift?: boolean
  compatibilityStatus?: 'compatible' | 'incompatible' | 'unavailable'
}
