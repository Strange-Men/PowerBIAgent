import type {
  AssistantMessage,
  ChatResponse,
  ConversationHistoryItem,
  ReportResource,
} from '../types'

const EMPTY_TEXT = '暂无符合条件的数据。你可以调整问题或筛选条件后再试。'
const ERROR_TEXT = '当前请求无法完成，请检查问题或稍后重试。'

function friendlyBusinessError(response: ChatResponse): string {
  const errorType = response.error_type || ''
  if (
    errorType === 'stale_instance' ||
    errorType === 'DESKTOP_STALE_INSTANCE'
  ) {
    return '当前选择的数据模型已关闭或失效，请刷新模型列表后重新选择。'
  }
  if (errorType.startsWith('deepseek_') || errorType.startsWith('LLM')) {
    return '语言分析服务暂不可用，请稍后重试。'
  }
  if (
    response.powerbi_mode === 'local_mcp' &&
    errorType === 'connection_error'
  ) {
    return 'Power BI Desktop 连接已中断，请确认 Desktop 和数据模型仍处于打开状态。'
  }
  if (errorType === 'ToolPolicyDeniedError' || errorType.includes('model')) {
    return '当前选择的数据模型不可用，请重新选择已连接模型。'
  }
  if (
    errorType.includes('semantic') ||
    errorType.includes('grounding') ||
    errorType.includes('validation')
  ) {
    return '当前数据模型无法支持这个问题，请调整问法或选择其他模型。'
  }
  return ERROR_TEXT
}

function contentForResponse(response: ChatResponse): {
  kind: AssistantMessage['kind']
  content: string
} {
  if (
    (response.response_type === 'clarification' ||
      response.terminal_state.includes('clarification')) &&
    response.clarification_question
  ) {
    return { kind: 'clarification', content: response.clarification_question }
  }
  if (
    (response.response_type === 'unsupported' ||
      response.terminal_state === 'unsupported') &&
    response.unsupported_reason
  ) {
    return { kind: 'unsupported', content: response.unsupported_reason }
  }
  if (response.error_type || response.terminal_state.includes('failed')) {
    return { kind: 'error', content: friendlyBusinessError(response) }
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
    ...(response.presentation ? { presentation: response.presentation } : {}),
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
    presentation: item.presentation,
    clarification_question: item.clarification_question,
    unsupported_reason: item.unsupported_reason,
    error_type: item.error_type,
    source_mode: '',
    idempotent_replay: false,
  }
  return { ...chatResponseToMessage(response), restored: true }
}

export function historyItemToMessages(
  item: ConversationHistoryItem,
): import('../types').ConversationMessage[] {
  const assistant = historyItemToMessage(item)
  if (!item.user_message?.trim()) return [assistant]
  return [
    {
      id: `user-${item.request_id}`,
      role: 'user',
      content: item.user_message.trim(),
    },
    assistant,
  ]
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
  const normalized = value?.replace(/^用户提问:\s*/, '').trim()
  if (!normalized) return '未命名对话'
  return normalized.length > 22 ? `${normalized.slice(0, 22)}…` : normalized
}
