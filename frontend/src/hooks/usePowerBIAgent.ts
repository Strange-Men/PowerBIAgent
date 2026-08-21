import { useCallback, useEffect, useMemo, useState } from 'react'
import {
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
  defaultSemanticModel,
  reportTemplateOptions,
  runtimeMode,
} from '../config'
import type {
  AssistantMessage,
  CatalogOption,
  ConversationMessage,
  ConversationReportItem,
  ConversationSummary,
} from '../types'

function requestId(): string {
  return globalThis.crypto.randomUUID()
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
  const [selectedSemanticModel, setSelectedSemanticModel] =
    useState<CatalogOption>(defaultSemanticModel)
  const [selectedReportTemplate, setSelectedReportTemplate] =
    useState<CatalogOption | null>(null)

  const refreshSidebar = useCallback(async () => {
    try {
      const page = await listRecentConversations(runtimeMode)
      setRecentConversations(page.items)
      const reports = await listRecentReports(
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
    const timer = window.setTimeout(() => void refreshSidebar(), 0)
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
      if (!normalized || sending) return

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
        await refreshSidebar()
      } catch (error) {
        const content =
          error instanceof Error
            ? error.message
            : '这次分析没有完成，请稍后重试。'
        const message: AssistantMessage = {
          id: `error-${id}`,
          role: 'assistant',
          kind: 'error',
          content,
        }
        setMessages((current) => [...current, message])
      } finally {
        setSending(false)
      }
    },
    [
      activeConversationId,
      refreshSidebar,
      selectedReportTemplate,
      selectedSemanticModel,
      sending,
    ],
  )

  const openConversation = useCallback(async (conversation: ConversationSummary) => {
    setLoadingConversation(true)
    try {
      const history = await getConversationHistory(
        runtimeMode,
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
  }, [])

  const search = useCallback(async (query: string) => {
    const page = await searchConversations(runtimeMode, query)
    return page.items
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
    recentReports,
    sending,
    loadingConversation,
    sidebarError,
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
