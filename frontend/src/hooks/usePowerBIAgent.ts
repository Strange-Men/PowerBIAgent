import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  discoverSemanticModels,
  getConversationHistory,
  listRecentConversations,
  listRecentReports,
  searchConversations,
  sendChat,
} from '../api/client'
import {
  chatResponseToMessage,
  conversationTitle,
  historyItemToMessage,
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
} from '../types'

function requestId(): string {
  return globalThis.crypto.randomUUID()
}

function discoveryErrorMessage(errorType: string | null): string | null {
  if (!errorType) return null
  if (errorType === 'powerbi_desktop_not_connected') {
    return 'Power BI Desktop 未连接，请先打开一个 PBIX 文件。'
  }
  if (errorType === 'powerbi_desktop_connection_failed') {
    return '已发现 Power BI Desktop，但当前数据模型无法连接。'
  }
  return '暂时无法获取可用数据模型。'
}

export function usePowerBIAgent() {
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [title, setTitle] = useState('新聊天')
  const [recentConversations, setRecentConversations] = useState<ConversationSummary[]>([])
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
  const [selectedReportTemplate, setSelectedReportTemplate] =
    useState<CatalogOption | null>(null)

  const refreshSidebar = useCallback(async (mode: RuntimeMode) => {
    try {
      const page = await listRecentConversations(mode)
      setRecentConversations(page.items)
      const reports = await listRecentReports(
        mode,
        page.items.map((item) => item.conversation_id),
      )
      setRecentReports(reports)
      setSidebarError(null)
    } catch {
      setSidebarError('会话记录暂不可用')
      setRecentConversations([])
      setRecentReports([])
    }
  }, [])

  useEffect(() => {
    const load = async () => {
      try {
        const catalog = await discoverSemanticModels()
        const options = catalog.items
          .filter((item) => item.available && item.connected)
          .map((item) => ({
            key: item.key,
            label: item.display_name,
            description:
              item.source === 'local_desktop'
                ? '当前已连接模型'
                : '开发测试模型',
          }))
        setEffectiveRuntimeMode(catalog.runtime_mode)
        setSemanticModelOptions(options)
        setSelectedSemanticModel((current) =>
          options.find((item) => item.key === current?.key) || options[0] || null,
        )
        setSemanticModelError(
          discoveryErrorMessage(catalog.error_type) ||
            (options.length === 0 ? '当前没有可用数据模型。' : null),
        )
        await refreshSidebar(catalog.runtime_mode)
      } catch (error) {
        setSemanticModelOptions([])
        setSelectedSemanticModel(null)
        setSemanticModelError(
          error instanceof Error ? error.message : '暂时无法获取可用数据模型。',
        )
        await refreshSidebar(initialRuntimeMode)
      } finally {
        setLoadingSemanticModels(false)
      }
    }
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [refreshSidebar])

  const startNewChat = useCallback(() => {
    setMessages([])
    setActiveConversationId(null)
    setTitle('新聊天')
    setSelectedReportTemplate(null)
  }, [])

  const submitMessage = useCallback(
    async (content: string) => {
      const normalized = content.trim()
      if (!normalized || sending || !selectedSemanticModel) return

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
        setActiveConversationId(response.conversation_id)
        setMessages((current) => [...current, chatResponseToMessage(response)])
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
    setLoadingConversation(true)
    try {
      const history = await getConversationHistory(
        effectiveRuntimeMode,
        conversation.conversation_id,
      )
      const restoredMessages = [...history.items]
        .sort((left, right) => left.created_at.localeCompare(right.created_at))
        .map(historyItemToMessage)
      setMessages(restoredMessages)
      setActiveConversationId(conversation.conversation_id)
      setTitle(conversationTitle(conversation.latest_analysis_goal))
    } catch (error) {
      const content =
        error instanceof Error ? error.message : '无法恢复该对话，请稍后重试。'
      setMessages([
        {
          id: `history-error-${conversation.conversation_id}`,
          role: 'assistant',
          kind: 'error',
          content,
        },
      ])
      setActiveConversationId(conversation.conversation_id)
      setTitle(conversationTitle(conversation.latest_analysis_goal))
    } finally {
      setLoadingConversation(false)
    }
  }, [effectiveRuntimeMode])

  const search = useCallback(async (query: string) => {
    const page = await searchConversations(effectiveRuntimeMode, query)
    return page.items
  }, [effectiveRuntimeMode])

  const hasRestoredHistory = useMemo(
    () => messages.some((message) => message.role === 'assistant' && message.restored),
    [messages],
  )

  return {
    messages,
    activeConversationId,
    title,
    recentConversations,
    recentReports,
    sending,
    loadingConversation,
    sidebarError,
    effectiveRuntimeMode,
    semanticModelOptions,
    loadingSemanticModels,
    semanticModelError,
    selectedSemanticModel,
    selectedReportTemplate,
    reportTemplateOptions,
    hasRestoredHistory,
    startNewChat,
    submitMessage,
    openConversation,
    search,
    setSelectedSemanticModel,
    setSelectedReportTemplate,
  }
}
