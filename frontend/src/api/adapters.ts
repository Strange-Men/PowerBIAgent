import type {
  AssistantMessage,
  ChatResponse,
  ConversationHistoryItem,
  ReportResource,
} from '../types'

const EMPTY_TEXT = '暂无符合条件的数据。你可以调整问题或筛选条件后再试。'
const ERROR_TEXT = '这次分析没有完成，请稍后重试。'

function contentForResponse(response: ChatResponse): {
  kind: AssistantMessage['kind']
  content: string
} {
  if (response.response_type === 'clarification' && response.clarification_question) {
    return { kind: 'clarification', content: response.clarification_question }
  }
  if (response.response_type === 'unsupported' && response.unsupported_reason) {
    return { kind: 'unsupported', content: response.unsupported_reason }
  }
  if (response.error_type || response.terminal_state.includes('failed')) {
    return { kind: 'error', content: response.answer?.trim() || ERROR_TEXT }
  }
  if (response.answer?.trim()) {
    return { kind: 'answer', content: response.answer.trim() }
  }
  if (response.report) {
    return { kind: 'answer', content: '报表已生成，可以查看或下载 HTML 文件。' }
  }
  return { kind: 'empty', content: EMPTY_TEXT }
}

export function chatResponseToMessage(response: ChatResponse): AssistantMessage {
  const content = contentForResponse(response)
  return {
    id: response.request_id,
    role: 'assistant',
    ...content,
    ...(isUsableReport(response.report) ? { report: response.report } : {}),
  }
}

export function historyItemToMessage(item: ConversationHistoryItem): AssistantMessage {
  const response: ChatResponse = {
    request_id: item.request_id,
    conversation_id: '',
    terminal_state: item.terminal_state,
    intent: item.intent,
    response_type: item.response_type,
    answer: item.answer,
    report: item.report,
    clarification_question: item.clarification_question,
    unsupported_reason: item.unsupported_reason,
    error_type: item.error_type,
    source_mode: '',
    idempotent_replay: false,
  }
  return { ...chatResponseToMessage(response), restored: true }
}

export function isUsableReport(report: ReportResource | null): report is ReportResource {
  return Boolean(
    report?.report_id &&
      report.view_reference === `/api/reports/${encodeURIComponent(report.report_id)}` &&
      report.download_reference ===
        `/api/reports/${encodeURIComponent(report.report_id)}/download`,
  )
}

export function conversationTitle(value: string | null | undefined): string {
  const normalized = value?.trim()
  if (!normalized) return '未命名对话'
  return normalized.length > 22 ? `${normalized.slice(0, 22)}…` : normalized
}
