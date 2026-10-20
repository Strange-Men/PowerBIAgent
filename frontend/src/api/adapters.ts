import { tr } from '../i18n'
import type {
  AssistantMessage,
  ChatResponse,
  ConversationHistoryItem,
  ReportResource,
} from '../types'
import { publicFailureMessage } from '../failure'

const emptyText = () => tr('errors:noMatchingDataTryChangingYourQuestionOrFilters')
const errorText = () => tr('errors:thisRequestCouldNotBeCompletedCheckYourQuestion')

function friendlyBusinessError(response: ChatResponse): string {
  if (response.failure) return publicFailureMessage(response.failure)
  const errorType = response.error_type || ''
  if (
    errorType === 'stale_instance' ||
    errorType === 'DESKTOP_STALE_INSTANCE'
  ) {
    return tr('errors:theSelectedDataModelIsNoLongerAvailableRefresh')
  }
  if (errorType === 'deepseek_connection_failed' || errorType === 'LLMConnectionError') {
    return tr('errors:theAiAnalysisServiceIsUnavailableTryAgainLater')
  }
  if (
    response.powerbi_mode === 'local_mcp' &&
    errorType === 'connection_error'
  ) {
    return tr('errors:thePowerBiDesktopConnectionWasLostCheckThat')
  }
  if (errorType === 'ToolPolicyDeniedError') {
    return tr('errors:theSelectedDataModelIsUnavailableSelectAConnected')
  }
  if (errorType === 'SemanticInterpretationError') {
    return tr('errors:thisModelCannotSupportThisQuestionRephraseItOr')
  }
  return errorText()
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
    return { kind: 'answer', content: tr('errors:yourReportIsReadyViewItOrDownloadThe') }
  }
  return { kind: 'empty', content: emptyText() }
}

export function chatResponseToMessage(response: ChatResponse): AssistantMessage {
  const content = contentForResponse(response)
  return {
    id: response.request_id,
    role: 'assistant',
    presentationAvailable:response.presentation_available,
    ...content,
    ...(isPresentableReport(response.report) ? { report: response.report } : {}),
    ...(response.presentation ? { presentation: response.presentation } : {}),
  }
}

export function historyItemToMessage(item: ConversationHistoryItem): AssistantMessage {
  const response: ChatResponse = {
    presentation_available:item.presentation_available,
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
    failure: item.failure,
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
  const bases=['/api/reports','/api/v1/cloud/reports']
  return Boolean(
    report?.report_id &&
      report.availability_status !== 'deleted' &&
      bases.some(base => report.view_reference === `${base}/${encodeURIComponent(report.report_id)}` &&
        report.download_reference === `${base}/${encodeURIComponent(report.report_id)}/download`),
  )
}

export function isPresentableReport(
  report: ReportResource | null,
): report is ReportResource {
  if (!report) return false
  if (report.availability_status === 'deleted') return Boolean(report.report_id)
  return isUsableReport(report)
}

export function conversationTitle(value: string | null | undefined): string {
  const normalized = value?.replace(/^用户提问:\s*/, '').trim()
  if (!normalized) return tr('errors:untitledConversation')
  return normalized.length > 22 ? `${normalized.slice(0, 22)}…` : normalized
}
