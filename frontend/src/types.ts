export type RuntimeMode = 'mock' | 'real'

export type PublicFailureCode =
  | 'REPORT_TEMPLATE_INCOMPATIBLE'
  | 'REPORT_TEMPLATE_UNAVAILABLE'
  | 'REPORT_DATA_UNAVAILABLE'
  | 'REPORT_EXECUTION_FAILED'
  | 'REPORT_RENDER_FAILED'
  | 'POWERBI_CONNECTION_LOST'
  | 'SEMANTIC_MODEL_STALE'
  | 'LLM_SERVICE_UNAVAILABLE'
  | 'REQUEST_TIMEOUT'
  | 'VALIDATION_FAILED'
  | 'INTERNAL_FAILURE'

export type FailureStage =
  | 'report_scope'
  | 'report_plan'
  | 'report_query_validation'
  | 'report_dax_execution'
  | 'sales_report_data_assembly'
  | 'sales_report_spec'
  | 'report_render_store'
  | 'memory_commit'
  | 'understanding'
  | 'grounding'
  | 'answer_generation'
  | 'tool_execution'
  | 'provider'
  | 'internal'

export type FailureRecoveryAction =
  | 'retry'
  | 'refresh_semantic_models'
  | 'reselect_semantic_model'
  | 'reselect_report_template'
  | 'edit_request'
  | 'none'

export interface FailureInfo {
  code: PublicFailureCode
  stage: FailureStage
  retryable: boolean
  recovery_action: FailureRecoveryAction
}

export interface ChatRequest {
  message: string
  conversation_id?: string
  request_id: string
  semantic_model_key: string
  report_template_key?: string
  llm_profile_key?: string
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

export interface PresentationField {
  canonical_field: string
  object_identity: string
  object_type: 'measure' | 'field'
  canonical_name: string
  locale: string
  display_name: string
  source: 'powerbi_metadata' | 'model_glossary' | 'registry' | 'bounded_translation' | 'fallback'
  schema_identity: string
  format_kind: 'auto' | 'integer' | 'decimal' | 'percentage' | 'amount' | 'date' | 'month' | 'text'
}

export interface PresentationDataset {
  result_id: string
  verified_fact_set_id: string
  semantic_model_key: string
  source_mode: RuntimeMode
  columns: string[]
  rows: PresentationCell[][]
  display_fields?: PresentationField[]
  formatted_rows?: string[][]
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
  failure?: FailureInfo | null
  source_mode: RuntimeMode | ''
  llm_mode?: string
  powerbi_mode?: string
  llm_profile_key?: string
  llm_model?: string
  llm_provider_protocol?: string
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
  resource_status?: 'ready' | 'failed'
  last_error_type?: string | null
  local_status?: 'processing' | 'failed' | 'ready'
  local_error?: string | null
}

export interface LLMProfileOption {
  profile_key: string
  display_name: string
  provider_protocol: 'mock' | 'openai_chat_completions'
  model: string
  available: boolean
  default: boolean
  unavailable_reason: string | null
}

export interface LLMProfileCatalog {
  items: LLMProfileOption[]
}

export interface ReportTemplateOption {
  template_key: string
  display_name: string
  description: string
  availability: 'available' | 'unavailable'
  compatibility_status: 'compatible' | 'partial' | 'incompatible' | 'unavailable'
  selectable: boolean
  available_section_count: number
  total_section_count: number
  reason_code?: string | null
}

export interface ReportTemplateCatalog {
  items: ReportTemplateOption[]
}

export interface ConversationFailureResult {
  runtime_mode: RuntimeMode
  conversation_id: string
  resource_status: 'failed'
  last_error_type: string
  updated_at: string
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
  failure?: FailureInfo | null
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
  createdAt: string
  updatedAt: string
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
  compatibilityStatus?: 'compatible' | 'partial' | 'incompatible' | 'unavailable'
}
