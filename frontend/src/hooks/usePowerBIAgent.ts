import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  archiveConversation,
  deleteConversation,
  deleteReport,
  discoverSemanticModels,
  getConversationHistory,
  listArchivedConversations,
  listRecentConversations,
  listRecentReports,
  renameConversation,
  restoreConversation,
  searchConversations,
  sendChat,
} from '../api/client'
import {
  chatResponseToMessage,
  conversationTitle,
  historyItemToMessages,
} from '../api/adapters'
import {
  initialRuntimeMode,
  reportTemplateOptions,
} from '../config'
import type {
  AssistantMessage,
  CatalogOption,
  ConversationMessage,
  ConversationReportItem,
  ConversationSummary,
  RuntimeMode,
  SemanticModelOption,
} from '../types'

function requestId(): string {
  return globalThis.crypto.randomUUID()
}

export function discoveryErrorMessage(errorType: string | null): string | null {
  if (!errorType) return null
  if (errorType === 'powerbi_desktop_not_connected') {
    return 'Power BI Desktop 未连接，请先打开一个 PBIX 文件。'
  }
  if (errorType === 'powerbi_multiple_desktop_instances') {
    return '检测到重复的 Desktop 实例身份，已安全停止模型发现。'
  }
  if (errorType === 'powerbi_desktop_connection_failed') {
    return '已发现 Power BI Desktop，但当前数据模型无法连接。'
  }
  return '暂时无法获取可用数据模型。'
}

export function catalogOptions(items: SemanticModelOption[]): CatalogOption[] {
  const visible = items.filter((item) => item.available && item.connected)
  const totals = visible.reduce<Record<string, number>>((counts, item) => {
    counts[item.display_name] = (counts[item.display_name] || 0) + 1
    return counts
  }, {})
  const seen: Record<string, number> = {}
  return visible.map((item) => {
    seen[item.display_name] = (seen[item.display_name] || 0) + 1
    const label =
      totals[item.display_name] > 1
        ? `${item.display_name}（实例 ${seen[item.display_name]}）`
        : item.display_name
    return {
      key: item.key,
      label,
      description:
        item.agent_compatible
          ? item.source === 'local_desktop'
            ? item.schema_drift
              ? '模型结构有更新，当前分析能力可用'
              : '当前已连接且可用于分析'
            : '开发测试模型'
          : item.compatibility_status === 'incompatible'
            ? '已连接，但缺少当前分析所需的业务字段或指标'
            : '已连接，但兼容性检查暂不可用',
      compatible: item.agent_compatible === true,
      selectable: item.selectable === true,
      schemaDrift: item.schema_drift === true,
      compatibilityStatus: item.compatibility_status || 'unavailable',
    }
  })
}

export function reconcileSemanticModelSelection(
  current: CatalogOption | null,
  options: CatalogOption[],
  allowDefault: boolean,
): { selected: CatalogOption | null; stale: boolean } {
  if (current) {
    const matched = options.find((item) => item.key === current.key)
    return matched ? { selected: matched, stale: false } : { selected: null, stale: true }
  }
  return {
    selected: allowDefault
      ? options.find((item) => item.compatible && item.selectable) || options[0] || null
      : null,
    stale: false,
  }
}

export function withoutDeletedReport(
  messages: ConversationMessage[],
  reportId: string,
): ConversationMessage[] {
  return messages.map((message) => {
    if (message.role !== 'assistant') return message
    const next: AssistantMessage = { ...message }
    if (next.report?.report_id === reportId) delete next.report
    if (next.presentation) {
      next.presentation = {
        ...next.presentation,
        blocks: next.presentation.blocks.filter(
          (block) => block.type !== 'report_attachment' || block.report_id !== reportId,
        ),
      }
    }
    return next
  })
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function usePowerBIAgent() {
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [title, setTitle] = useState('新聊天')
  const [recentConversations, setRecentConversations] = useState<ConversationSummary[]>([])
  const [archivedConversations, setArchivedConversations] = useState<ConversationSummary[]>([])
  const [recentReports, setRecentReports] = useState<ConversationReportItem[]>([])
  const [sending, setSending] = useState(false)
  const [loadingConversation, setLoadingConversation] = useState(false)
  const [sidebarError, setSidebarError] = useState<string | null>(null)
  const [effectiveRuntimeMode, setEffectiveRuntimeMode] =
    useState<RuntimeMode>(initialRuntimeMode)
  const [semanticModelOptions, setSemanticModelOptions] = useState<CatalogOption[]>([])
  const [loadingSemanticModels, setLoadingSemanticModels] = useState(true)
  const [semanticModelError, setSemanticModelError] = useState<string | null>(null)
  const [selectedSemanticModel, setSelectedSemanticModel] =
    useState<CatalogOption | null>(null)
  const selectedSemanticModelRef = useRef<CatalogOption | null>(null)
  const semanticModelsLoadedRef = useRef(false)
  const activeConversationIdRef = useRef<string | null>(null)
  const historyGenerationRef = useRef(0)
  const historyAbortRef = useRef<AbortController | null>(null)
  const [selectedReportTemplate, setSelectedReportTemplate] =
    useState<CatalogOption | null>(null)

  const cancelHistoryRequest = useCallback(() => {
    historyGenerationRef.current += 1
    historyAbortRef.current?.abort()
    historyAbortRef.current = null
    setLoadingConversation(false)
  }, [])

  const refreshSidebar = useCallback(async (mode: RuntimeMode) => {
    try {
      const [page, archivedPage] = await Promise.all([
        listRecentConversations(mode),
        listArchivedConversations(mode),
      ])
      setRecentConversations(page.items)
      setArchivedConversations(archivedPage.items)
      const reports = await listRecentReports(
        mode,
        page.items.map((item) => item.conversation_id),
      )
      setRecentReports(reports)
      setSidebarError(null)
    } catch {
      setSidebarError('会话记录暂不可用')
      setRecentConversations([])
      setArchivedConversations([])
      setRecentReports([])
    }
  }, [])

  const refreshSemanticModels = useCallback(async () => {
    setLoadingSemanticModels(true)
    try {
      const catalog = await discoverSemanticModels()
      const options = catalogOptions(catalog.items)
      const reconciled = reconcileSemanticModelSelection(
        selectedSemanticModelRef.current,
        options,
        !semanticModelsLoadedRef.current,
      )
      setEffectiveRuntimeMode(catalog.runtime_mode)
      setSemanticModelOptions(options)
      selectedSemanticModelRef.current = reconciled.selected
      setSelectedSemanticModel(reconciled.selected)
      setSemanticModelError(
        (reconciled.stale
          ? '当前选择的数据模型已关闭或失效，请刷新后重新选择。'
          : discoveryErrorMessage(catalog.error_type)) ||
          (options.length === 0 ? '当前没有可用数据模型。' : null),
      )
      await refreshSidebar(catalog.runtime_mode)
    } catch (error) {
      setSemanticModelOptions([])
      selectedSemanticModelRef.current = null
      setSelectedSemanticModel(null)
      setSemanticModelError(
        error instanceof Error ? error.message : '暂时无法获取可用数据模型。',
      )
      await refreshSidebar(initialRuntimeMode)
    } finally {
      semanticModelsLoadedRef.current = true
      setLoadingSemanticModels(false)
    }
  }, [refreshSidebar])

  useEffect(() => {
    const timer = window.setTimeout(() => void refreshSemanticModels(), 0)
    return () => {
      window.clearTimeout(timer)
      cancelHistoryRequest()
    }
  }, [cancelHistoryRequest, refreshSemanticModels])

  const selectSemanticModel = useCallback((option: CatalogOption) => {
    const changed = selectedSemanticModelRef.current?.key !== option.key
    selectedSemanticModelRef.current = option
    setSelectedSemanticModel(option)
    setSemanticModelError(null)
    if (changed) {
      cancelHistoryRequest()
      activeConversationIdRef.current = null
      setActiveConversationId(null)
      setMessages([])
      setTitle('新聊天')
      setSelectedReportTemplate(null)
    }
  }, [cancelHistoryRequest])

  const startNewChat = useCallback(() => {
    cancelHistoryRequest()
    setMessages([])
    activeConversationIdRef.current = null
    setActiveConversationId(null)
    setTitle('新聊天')
    setSelectedReportTemplate(null)
    setLoadingConversation(false)
  }, [cancelHistoryRequest])

  const submitMessage = useCallback(
    async (content: string) => {
      const normalized = content.trim()
      if (
        !normalized ||
        sending ||
        !selectedSemanticModel?.compatible ||
        selectedSemanticModel.selectable === false
      ) return

      const id = requestId()
      setMessages((current) => [
        ...current,
        { id: `user-${id}`, role: 'user', content: normalized },
      ])
      if (!activeConversationId) setTitle(conversationTitle(normalized))
      setSending(true)

      try {
        const response = await sendChat({
          message: normalized,
          request_id: id,
          semantic_model_key: selectedSemanticModel.key,
          ...(activeConversationId
            ? { conversation_id: activeConversationId }
            : {}),
          ...(selectedReportTemplate
            ? { report_template_key: selectedReportTemplate.key }
            : {}),
        })
        activeConversationIdRef.current = response.conversation_id
        setActiveConversationId(response.conversation_id)
        setMessages((current) => [...current, chatResponseToMessage(response)])
        if (
          response.error_type === 'stale_instance' ||
          response.error_type === 'DESKTOP_STALE_INSTANCE'
        ) {
          selectedSemanticModelRef.current = null
          setSelectedSemanticModel(null)
          setSemanticModelError(
            '当前选择的数据模型已关闭或失效，请刷新后重新选择。',
          )
        }
        await refreshSidebar(
          response.source_mode === 'mock' || response.source_mode === 'real'
            ? response.source_mode
            : effectiveRuntimeMode,
        )
      } catch (error) {
        const content =
          error instanceof Error
            ? error.message
            : '当前请求无法完成，请稍后重试。'
        const message: AssistantMessage = {
          id: `error-${id}`,
          role: 'assistant',
          kind: 'error',
          content,
        }
        setMessages((current) => [...current, message])
      } finally {
        setSelectedReportTemplate(null)
        setSending(false)
      }
    },
    [
      activeConversationId,
      refreshSidebar,
      selectedReportTemplate,
      selectedSemanticModel,
      sending,
      effectiveRuntimeMode,
    ],
  )

  const openConversation = useCallback(async (conversation: ConversationSummary) => {
    cancelHistoryRequest()
    const generation = historyGenerationRef.current
    const controller = new AbortController()
    historyAbortRef.current = controller
    const conversationId = conversation.conversation_id
    activeConversationIdRef.current = conversationId
    setActiveConversationId(conversationId)
    setMessages([])
    setTitle(conversationTitle(conversation.title || conversation.latest_analysis_goal))
    setLoadingConversation(true)
    try {
      const history = await getConversationHistory(
        effectiveRuntimeMode,
        conversationId,
        controller.signal,
      )
      if (
        controller.signal.aborted ||
        generation !== historyGenerationRef.current ||
        activeConversationIdRef.current !== conversationId ||
        history.conversation_id !== conversationId
      ) return
      const restoredMessages = [...history.items]
        .sort((left, right) => left.created_at.localeCompare(right.created_at))
        .flatMap(historyItemToMessages)
      setMessages(restoredMessages)
      setTitle(conversationTitle(history.title || conversation.title || conversation.latest_analysis_goal))
    } catch (error) {
      if (
        isAbortError(error) ||
        generation !== historyGenerationRef.current ||
        activeConversationIdRef.current !== conversationId
      ) return
      const content =
        error instanceof Error ? error.message : '无法恢复该对话，请稍后重试。'
      setMessages([
        {
          id: `history-error-${conversationId}`,
          role: 'assistant',
          kind: 'error',
          content,
        },
      ])
      setTitle(conversationTitle(conversation.title || conversation.latest_analysis_goal))
    } finally {
      if (generation === historyGenerationRef.current) {
        historyAbortRef.current = null
        setLoadingConversation(false)
      }
    }
  }, [cancelHistoryRequest, effectiveRuntimeMode])

  const search = useCallback(async (query: string) => {
    const page = await searchConversations(effectiveRuntimeMode, query)
    return page.items
  }, [effectiveRuntimeMode])

  const rename = useCallback(async (conversation: ConversationSummary, nextTitle: string) => {
    const result = await renameConversation(
      effectiveRuntimeMode,
      conversation.conversation_id,
      nextTitle,
    )
    if (activeConversationId === conversation.conversation_id) setTitle(result.title)
    await refreshSidebar(effectiveRuntimeMode)
  }, [activeConversationId, effectiveRuntimeMode, refreshSidebar])

  const archive = useCallback(async (conversation: ConversationSummary) => {
    cancelHistoryRequest()
    await archiveConversation(effectiveRuntimeMode, conversation.conversation_id)
    if (activeConversationId === conversation.conversation_id) startNewChat()
    await refreshSidebar(effectiveRuntimeMode)
  }, [activeConversationId, cancelHistoryRequest, effectiveRuntimeMode, refreshSidebar, startNewChat])

  const remove = useCallback(async (conversation: ConversationSummary) => {
    cancelHistoryRequest()
    await deleteConversation(effectiveRuntimeMode, conversation.conversation_id)
    if (activeConversationId === conversation.conversation_id) startNewChat()
    await refreshSidebar(effectiveRuntimeMode)
  }, [activeConversationId, cancelHistoryRequest, effectiveRuntimeMode, refreshSidebar, startNewChat])

  const restore = useCallback(async (conversation: ConversationSummary) => {
    cancelHistoryRequest()
    await restoreConversation(effectiveRuntimeMode, conversation.conversation_id)
    await refreshSidebar(effectiveRuntimeMode)
  }, [cancelHistoryRequest, effectiveRuntimeMode, refreshSidebar])

  const removeReport = useCallback(async (report: ConversationReportItem) => {
    await deleteReport(report.report_id)
    setRecentReports((current) =>
      current.filter((item) => item.report_id !== report.report_id),
    )
    setMessages((current) => withoutDeletedReport(current, report.report_id))
  }, [])

  const hasRestoredHistory = useMemo(
    () => messages.some((message) => message.role === 'assistant' && message.restored),
    [messages],
  )

  return {
    messages,
    activeConversationId,
    title,
    recentConversations,
    archivedConversations,
    recentReports,
    sending,
    loadingConversation,
    sidebarError,
    effectiveRuntimeMode,
    semanticModelOptions,
    refreshSemanticModels,
    loadingSemanticModels,
    semanticModelError,
    selectedSemanticModel,
    semanticModelCompatibilityNotice:
      selectedSemanticModel && !selectedSemanticModel.compatible
        ? selectedSemanticModel.compatibilityStatus === 'incompatible'
          ? '当前模型已连接，但缺少 PowerBIAgent 当前分析所需的部分业务字段或指标。'
          : '当前模型已连接，但暂时无法完成兼容性检查，请稍后重试。'
        : null,
    selectedReportTemplate,
    reportTemplateOptions,
    hasRestoredHistory,
    startNewChat,
    submitMessage,
    openConversation,
    search,
    rename,
    archive,
    restore,
    remove,
    removeReport,
    setSelectedSemanticModel: selectSemanticModel,
    setSelectedReportTemplate,
  }
}
