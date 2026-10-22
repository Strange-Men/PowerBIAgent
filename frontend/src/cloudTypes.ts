export interface CloudModel {
  key: string
  display_name: string
  workspace_display_name: string
  source: 'fabric_iq'
  accessibility: 'available'
}

export interface CloudCatalog {
  product_mode?: boolean
  persistence_enabled?: boolean
  status: 'ready' | 'partial' | 'empty' | 'forbidden' | 'error'
  runtime_mode: 'real'
  items: CloudModel[]
  workspace_scope_complete: boolean
  authorization_scope_complete?: boolean
  unverified_count?: number
  individual_share_coverage: 'configured_seeds_only' | 'not_applicable_test_scope'
  coverage_scope?: 'workspace_membership_and_configured_seeds' | 'approved_test_resources'
  inaccessible_count: number
  error_type: string | null
}

export interface CloudCatalogEntry {
  key: string
  display_name: string
  kind: 'Workspace' | 'SemanticModel' | 'Report'
}

export interface CloudCatalogPage {
  items: CloudCatalogEntry[]
  next_cursor: string | null
  partial: boolean
  coverage: 'workspace_membership_only'
}

export interface CloudWorkspaceStatus {
  persistence_ready?: boolean
  persistence_reason?: string | null
  report_templates?: import('./types').ReportTemplateCatalog | null
  selected_model_key: string | null
  conversation_id: string | null
  generation: number
  execution_ready: boolean
  blockers: Array<'numeric_contract' | 'query_completeness' | 'operator_approval'>
}
