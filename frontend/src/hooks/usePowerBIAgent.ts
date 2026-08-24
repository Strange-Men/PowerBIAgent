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
  renameReport,
  restoreConversation,
  searchConversations,
  sendChat,
} from '../api/client'
import {
  chatResponseToMessage,
  conversationTitle,
  historyItemToMessages,
} from '../api/adapters'
import { initialRuntimeMode, reportTemplateOptions } from '../config'
import type {
  AssistantMessage,
  BatchOperationResult,
  CatalogOption,
  ConversationMessage,
  ConversationReportItem,
  ConversationSession,
  ConversationSummary,
  RuntimeMode,
  SemanticModelOption,
} from '../types'

const MAX_BATCH_ITEMS = 20

function newId(): string {
  return globalThis.crypto.randomUUID()
}

function createSession(
  conversationId: string,
  title = '新聊天',
): ConversationSession {
  return {
    clientConversationId: conversationId,
    title,
    messages: [],
    pendingRequests: [],
    sending: false,
    loadingHistory: false,
    error: null,
    status: 'draft',
    restored: false,
  }
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
      description: item.agent_compatible
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
    return matched
      ? { selected: matched, stale: false }
      : { selected: null, stale: true }
  }
  return {
    selected: allowDefault
      ? options.find((item) => item.compatible && item.selectable) ||
        options[0] ||
        null
      : null,
    stale: false,
  }
}

export function withoutDeletedReport(
  messages: ConversationMessage[],
  reportId: string,
  displayTitle?: string,
): ConversationMessage[] {
  return messages.map((message) => {
    if (message.role !== 'assistant' || message.report?.report_id !== reportId) {
      return message
    }
    return {
      ...message,
      report: {
        ...message.report,
        display_title:
          displayTitle || message.report.display_title || '销售分析报告',
        availability_status: 'deleted',
        view_reference: '',
        download_reference: '',
        content_hash: '',
      },
    }
  })
}

function withRenamedReport(
  messages: ConversationMessage[],
  reportId: string,
  displayTitle: string,
): ConversationMessage[] {
  return messages.map((message) =>
    message.role === 'assistant' && message.report?.report_id === reportId
      ? {
          ...message,
          report: { ...message.report, display_title: displayTitle },
        }
      : message,
  )
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function failureReason(error: unknown): string {
  return error instanceof Error ? error.message : '操作未完成，请稍后重试。'
}

function assertBatchLimit(ids: string[]): string[] {
  const unique = [...new Set(ids)]
  if (unique.length > MAX_BATCH_ITEMS) {
    throw new Error(`单次最多管理 ${MAX_BATCH_ITEMS} 项资源。`)
  }
  return unique
}

export function usePowerBIAgent() {
  const [sessions, setSessions] = useState<Record<string, ConversationSession>>(
    {},
  )
  const sessionsRef = useRef<Record<string, ConversationSession>>({})
  const runningConversationIdsRef = useRef(new Set<string>())
  const removedConversationIdsRef = useRef(new Set<string>())
  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    null,
  )
  const activeConversationIdRef = useRef<string | null>(null)
  const [persistedRecent, setPersistedRecent] = useState<ConversationSummary[]>([])
  const [archivedConversations, setArchivedConversations] = useState<
    ConversationSummary[]
  >([])
  const [recentReports, setRecentReports] = useState<ConversationReportItem[]>([])
  const [sidebarError, setSidebarError] = useState<string | null>(null)
  const [effectiveRuntimeMode, setEffectiveRuntimeMode] =
    useState<RuntimeMode>(initialRuntimeMode)
  const [semanticModelOptions, setSemanticModelOptions] = useState<CatalogOption[]>(
    [],
  )
  const [loadingSemanticModels, setLoadingSemanticModels] = useState(true)
  const [semanticModelError, setSemanticModelError] = useState<string | null>(null)
  const [selectedSemanticModel, setSelectedSemanticModel] =
    useState<CatalogOption | null>(null)
  const selectedSemanticModelRef = useRef<CatalogOption | null>(null)
  const semanticModelsLoadedRef = useRef(false)
  const sidebarRefreshGenerationRef = useRef(0)
  const historyGenerationRef = useRef(0)
  const historyAbortRef = useRef<AbortController | null>(null)
  const historyConversationRef = useRef<string | null>(null)
  const [selectedReportTemplate, setSelectedReportTemplateState] =
    useState<CatalogOption | null>(null)
  const selectedReportTemplateRef = useRef<CatalogOption | null>(null)

  const replaceSessions = useCallback(
    (
      updater: (
        current: Record<string, ConversationSession>,
      ) => Record<string, ConversationSession>,
    ) => {
      const next = updater(sessionsRef.current)
      sessionsRef.current = next
      setSessions(next)
    },
    [],
  )

  const updateSession = useCallback(
    (
      conversationId: string,
      updater: (session: ConversationSession) => ConversationSession,
    ) => {
      replaceSessions((current) => {
        if (removedConversationIdsRef.current.has(conversationId)) return current
        const existing = current[conversationId] || createSession(conversationId)
        return { ...current, [conversationId]: updater(existing) }
      })
    },
    [replaceSessions],
  )

  const activate = useCallback((conversationId: string | null) => {
    activeConversationIdRef.current = conversationId
    setActiveConversationId(conversationId)
  }, [])

  const setSelectedReportTemplate = useCallback(
    (option: CatalogOption | null) => {
      selectedReportTemplateRef.current = option
      setSelectedReportTemplateState(option)
    },
    [],
  )

  const cancelHistoryRequest = useCallback(
    (conversationId?: string) => {
      if (
        conversationId &&
        historyConversationRef.current !== conversationId
      ) {
        return
      }
      const owner = historyConversationRef.current
      historyGenerationRef.current += 1
      historyAbortRef.current?.abort()
      historyAbortRef.current = null
      historyConversationRef.current = null
      if (owner) {
        updateSession(owner, (session) => ({
          ...session,
          loadingHistory: false,
        }))
      }
    },
    [updateSession],
  )

  const refreshSidebar = useCallback(async (mode: RuntimeMode) => {
    const generation = ++sidebarRefreshGenerationRef.current
    try {
      const [page, archivedPage] = await Promise.all([
        listRecentConversations(mode),
        listArchivedConversations(mode),
      ])
      const reports = await listRecentReports(
        mode,
        page.items.map((item) => item.conversation_id),
      )
      if (generation !== sidebarRefreshGenerationRef.current) return
      setPersistedRecent(page.items)
      setArchivedConversations(archivedPage.items)
      setRecentReports(reports)
      setSidebarError(null)
    } catch {
      if (generation === sidebarRefreshGenerationRef.current) {
        setSidebarError('会话记录暂不可用')
      }
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
      historyGenerationRef.current += 1
      historyAbortRef.current?.abort()
    }
  }, [refreshSemanticModels])

  const selectSemanticModel = useCallback(
    (option: CatalogOption) => {
      const changed = selectedSemanticModelRef.current?.key !== option.key
      selectedSemanticModelRef.current = option
      setSelectedSemanticModel(option)
      setSemanticModelError(null)
      if (changed) {
        cancelHistoryRequest()
        activate(null)
        setSelectedReportTemplate(null)
      }
    },
    [activate, cancelHistoryRequest, setSelectedReportTemplate],
  )

  const startNewChat = useCallback(() => {
    cancelHistoryRequest()
    const conversationId = newId()
    replaceSessions((current) => ({
      ...current,
      [conversationId]: createSession(conversationId),
    }))
    removedConversationIdsRef.current.delete(conversationId)
    activate(conversationId)
    setSelectedReportTemplate(null)
    return conversationId
  }, [activate, cancelHistoryRequest, replaceSessions, setSelectedReportTemplate])

  const submitMessage = useCallback(
    async (content: string) => {
      const normalized = content.trim()
      const model = selectedSemanticModelRef.current
      if (!normalized || !model?.compatible || model.selectable === false) return

      let conversationId = activeConversationIdRef.current
      if (!conversationId) {
        conversationId = newId()
        const generatedId = conversationId
        replaceSessions((current) => ({
          ...current,
          [generatedId]: createSession(generatedId),
        }))
        removedConversationIdsRef.current.delete(generatedId)
        activate(conversationId)
      }
      if (runningConversationIdsRef.current.has(conversationId)) return

      const id = newId()
      const template = selectedReportTemplateRef.current
      runningConversationIdsRef.current.add(conversationId)
      updateSession(conversationId, (session) => ({
        ...session,
        title:
          session.status === 'draft'
            ? conversationTitle(normalized)
            : session.title,
        messages: [
          ...session.messages,
          { id: `user-${id}`, role: 'user', content: normalized },
        ],
        pendingRequests: [...session.pendingRequests, id],
        sending: true,
        loadingHistory: false,
        error: null,
        status: 'processing',
        restored: false,
      }))

      try {
        const response = await sendChat({
          message: normalized,
          conversation_id: conversationId,
          request_id: id,
          semantic_model_key: model.key,
          ...(template ? { report_template_key: template.key } : {}),
        })
        if (response.conversation_id !== conversationId) {
          throw new Error('服务返回了不匹配的对话身份，已停止写入。')
        }
        updateSession(conversationId, (session) => ({
          ...session,
          serverConversationId: response.conversation_id,
          messages: [...session.messages, chatResponseToMessage(response)],
          pendingRequests: session.pendingRequests.filter(
            (request) => request !== id,
          ),
          sending: false,
          error: response.error_type ? '当前请求未完成。' : null,
          status: response.error_type ? 'failed' : 'ready',
        }))
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
        const errorText =
          error instanceof Error
            ? error.message
            : '当前请求无法完成，请稍后重试。'
        const message: AssistantMessage = {
          id: `error-${id}`,
          role: 'assistant',
          kind: 'error',
          content: errorText,
        }
        updateSession(conversationId, (session) => ({
          ...session,
          messages: [...session.messages, message],
          pendingRequests: session.pendingRequests.filter(
            (request) => request !== id,
          ),
          sending: false,
          error: errorText,
          status: 'failed',
        }))
      } finally {
        runningConversationIdsRef.current.delete(conversationId)
        if (
          activeConversationIdRef.current === conversationId &&
          selectedReportTemplateRef.current?.key === template?.key
        ) {
          setSelectedReportTemplate(null)
        }
      }
    },
    [
      activate,
      effectiveRuntimeMode,
      refreshSidebar,
      replaceSessions,
      setSelectedReportTemplate,
      updateSession,
    ],
  )

  const openConversation = useCallback(
    async (conversation: ConversationSummary) => {
      cancelHistoryRequest()
      const conversationId = conversation.conversation_id
      activate(conversationId)
      const local = sessionsRef.current[conversationId]
      if (
        local &&
        (local.messages.length > 0 ||
          local.sending ||
          conversation.local_status === 'processing' ||
          conversation.local_status === 'failed')
      ) {
        return
      }

      const generation = historyGenerationRef.current
      const controller = new AbortController()
      historyAbortRef.current = controller
      historyConversationRef.current = conversationId
      updateSession(conversationId, (session) => ({
        ...session,
        title: conversationTitle(
          conversation.title || conversation.latest_analysis_goal,
        ),
        messages: [],
        loadingHistory: true,
        error: null,
        status: 'ready',
      }))
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
        ) {
          return
        }
        const restoredMessages = [...history.items]
          .sort((left, right) => left.created_at.localeCompare(right.created_at))
          .flatMap(historyItemToMessages)
        updateSession(conversationId, (session) => ({
          ...session,
          serverConversationId: conversationId,
          title: conversationTitle(
            history.title ||
              conversation.title ||
              conversation.latest_analysis_goal,
          ),
          messages: restoredMessages,
          loadingHistory: false,
          error: null,
          status: 'ready',
          restored: true,
        }))
      } catch (error) {
        if (
          isAbortError(error) ||
          generation !== historyGenerationRef.current ||
          activeConversationIdRef.current !== conversationId
        ) {
          return
        }
        const errorText =
          error instanceof Error
            ? error.message
            : '无法恢复该对话，请稍后重试。'
        updateSession(conversationId, (session) => ({
          ...session,
          messages: [
            {
              id: `history-error-${conversationId}`,
              role: 'assistant',
              kind: 'error',
              content: errorText,
            },
          ],
          loadingHistory: false,
          error: errorText,
          status: 'failed',
        }))
      } finally {
        if (generation === historyGenerationRef.current) {
          historyAbortRef.current = null
          historyConversationRef.current = null
          updateSession(conversationId, (session) => ({
            ...session,
            loadingHistory: false,
          }))
        }
      }
    },
    [activate, cancelHistoryRequest, effectiveRuntimeMode, updateSession],
  )

  const search = useCallback(
    async (query: string) =>
      (await searchConversations(effectiveRuntimeMode, query)).items,
    [effectiveRuntimeMode],
  )

  const rename = useCallback(
    async (conversation: ConversationSummary, nextTitle: string) => {
      const result = await renameConversation(
        effectiveRuntimeMode,
        conversation.conversation_id,
        nextTitle,
      )
      updateSession(conversation.conversation_id, (session) => ({
        ...session,
        title: result.title,
      }))
      await refreshSidebar(effectiveRuntimeMode)
    },
    [effectiveRuntimeMode, refreshSidebar, updateSession],
  )

  const clearConversationLocally = useCallback(
    (conversationId: string) => {
      removedConversationIdsRef.current.add(conversationId)
      runningConversationIdsRef.current.delete(conversationId)
      replaceSessions((current) => {
        const next = { ...current }
        delete next[conversationId]
        return next
      })
      if (activeConversationIdRef.current === conversationId) activate(null)
      setPersistedRecent((current) =>
        current.filter((item) => item.conversation_id !== conversationId),
      )
      setArchivedConversations((current) =>
        current.filter((item) => item.conversation_id !== conversationId),
      )
      setRecentReports((current) =>
        current.filter((item) => item.conversation_id !== conversationId),
      )
    },
    [activate, replaceSessions],
  )

  const archive = useCallback(
    async (conversation: ConversationSummary) => {
      if (runningConversationIdsRef.current.has(conversation.conversation_id)) {
        throw new Error('对话仍在分析，完成后再归档。')
      }
      cancelHistoryRequest(conversation.conversation_id)
      await archiveConversation(effectiveRuntimeMode, conversation.conversation_id)
      if (activeConversationIdRef.current === conversation.conversation_id) {
        activate(null)
      }
      replaceSessions((current) => {
        const next = { ...current }
        delete next[conversation.conversation_id]
        return next
      })
      setPersistedRecent((current) =>
        current.filter(
          (item) => item.conversation_id !== conversation.conversation_id,
        ),
      )
      await refreshSidebar(effectiveRuntimeMode)
    },
    [
      activate,
      cancelHistoryRequest,
      effectiveRuntimeMode,
      refreshSidebar,
      replaceSessions,
    ],
  )

  const remove = useCallback(
    async (conversation: ConversationSummary) => {
      if (runningConversationIdsRef.current.has(conversation.conversation_id)) {
        throw new Error('对话仍在分析，完成后再删除。')
      }
      cancelHistoryRequest(conversation.conversation_id)
      const persisted =
        persistedRecent.some(
          (item) => item.conversation_id === conversation.conversation_id,
        ) ||
        archivedConversations.some(
          (item) => item.conversation_id === conversation.conversation_id,
        )
      if (persisted) {
        await deleteConversation(
          effectiveRuntimeMode,
          conversation.conversation_id,
        )
      }
      clearConversationLocally(conversation.conversation_id)
      if (persisted) await refreshSidebar(effectiveRuntimeMode)
    },
    [
      archivedConversations,
      cancelHistoryRequest,
      clearConversationLocally,
      effectiveRuntimeMode,
      persistedRecent,
      refreshSidebar,
    ],
  )

  const restore = useCallback(
    async (conversation: ConversationSummary) => {
      await restoreConversation(effectiveRuntimeMode, conversation.conversation_id)
      await refreshSidebar(effectiveRuntimeMode)
    },
    [effectiveRuntimeMode, refreshSidebar],
  )

  const removeReport = useCallback(
    async (report: ConversationReportItem) => {
      await deleteReport(report.report_id)
      setRecentReports((current) =>
        current.filter((item) => item.report_id !== report.report_id),
      )
      replaceSessions((current) =>
        Object.fromEntries(
          Object.entries(current).map(([id, session]) => [
            id,
            {
              ...session,
              messages: withoutDeletedReport(
                session.messages,
                report.report_id,
                report.display_title,
              ),
            },
          ]),
        ),
      )
    },
    [replaceSessions],
  )

  const renameReportResource = useCallback(
    async (report: ConversationReportItem, displayTitle: string) => {
      const renamed = await renameReport(report.report_id, displayTitle)
      setRecentReports((current) =>
        current.map((item) =>
          item.report_id === report.report_id
            ? { ...item, display_title: renamed.display_title }
            : item,
        ),
      )
      replaceSessions((current) =>
        Object.fromEntries(
          Object.entries(current).map(([id, session]) => [
            id,
            {
              ...session,
              messages: withRenamedReport(
                session.messages,
                report.report_id,
                renamed.display_title,
              ),
            },
          ]),
        ),
      )
    },
    [replaceSessions],
  )

  const bulkRemoveConversations = useCallback(
    async (items: ConversationSummary[]): Promise<BatchOperationResult> => {
      const ids = assertBatchLimit(items.map((item) => item.conversation_id))
      const persistedIds = new Set([
        ...persistedRecent.map((item) => item.conversation_id),
        ...archivedConversations.map((item) => item.conversation_id),
      ])
      const results = await Promise.allSettled(
        ids.map((id) =>
          runningConversationIdsRef.current.has(id)
            ? Promise.reject(new Error('对话仍在分析，完成后再删除。'))
            : persistedIds.has(id)
            ? deleteConversation(effectiveRuntimeMode, id)
            : Promise.resolve(),
        ),
      )
      const outcome: BatchOperationResult = { succeededIds: [], failed: [] }
      results.forEach((result, index) => {
        const id = ids[index]
        if (result.status === 'fulfilled') {
          outcome.succeededIds.push(id)
          clearConversationLocally(id)
        } else {
          outcome.failed.push({ id, reason: failureReason(result.reason) })
        }
      })
      await refreshSidebar(effectiveRuntimeMode)
      return outcome
    },
    [
      archivedConversations,
      clearConversationLocally,
      effectiveRuntimeMode,
      persistedRecent,
      refreshSidebar,
    ],
  )

  const bulkRestoreConversations = useCallback(
    async (items: ConversationSummary[]): Promise<BatchOperationResult> => {
      const ids = assertBatchLimit(items.map((item) => item.conversation_id))
      const results = await Promise.allSettled(
        ids.map((id) => restoreConversation(effectiveRuntimeMode, id)),
      )
      const outcome: BatchOperationResult = { succeededIds: [], failed: [] }
      results.forEach((result, index) => {
        const id = ids[index]
        if (result.status === 'fulfilled') outcome.succeededIds.push(id)
        else outcome.failed.push({ id, reason: failureReason(result.reason) })
      })
      await refreshSidebar(effectiveRuntimeMode)
      return outcome
    },
    [effectiveRuntimeMode, refreshSidebar],
  )

  const bulkRemoveReports = useCallback(
    async (items: ConversationReportItem[]): Promise<BatchOperationResult> => {
      const byId = new Map(items.map((item) => [item.report_id, item]))
      const ids = assertBatchLimit([...byId.keys()])
      const results = await Promise.allSettled(ids.map((id) => deleteReport(id)))
      const outcome: BatchOperationResult = { succeededIds: [], failed: [] }
      const successfulReports = new Map<string, ConversationReportItem>()
      results.forEach((result, index) => {
        const id = ids[index]
        if (result.status === 'fulfilled') {
          outcome.succeededIds.push(id)
          const report = byId.get(id)
          if (report) successfulReports.set(id, report)
        } else {
          outcome.failed.push({ id, reason: failureReason(result.reason) })
        }
      })
      if (successfulReports.size > 0) {
        setRecentReports((current) =>
          current.filter((item) => !successfulReports.has(item.report_id)),
        )
        replaceSessions((current) =>
          Object.fromEntries(
            Object.entries(current).map(([sessionId, session]) => [
              sessionId,
              {
                ...session,
                messages: [...successfulReports.values()].reduce(
                  (messages, report) =>
                    withoutDeletedReport(
                      messages,
                      report.report_id,
                      report.display_title,
                    ),
                  session.messages,
                ),
              },
            ]),
          ),
        )
      }
      return outcome
    },
    [replaceSessions],
  )

  const recentConversations = useMemo(() => {
    const persisted = new Map(
      persistedRecent.map((conversation) => [
        conversation.conversation_id,
        conversation,
      ]),
    )
    const localRows = Object.values(sessions)
      .filter((session) => session.status !== 'draft')
      .map<ConversationSummary>((session) => {
        const stored = persisted.get(session.clientConversationId)
        persisted.delete(session.clientConversationId)
        const timestamp = new Date().toISOString()
        return {
          runtime_mode: effectiveRuntimeMode,
          conversation_id: session.clientConversationId,
          created_at: stored?.created_at || timestamp,
          updated_at: stored?.updated_at || timestamp,
          archived_at: null,
          title: session.title,
          latest_request_id:
            session.pendingRequests.at(-1) || stored?.latest_request_id || null,
          latest_terminal_state:
            session.status === 'processing'
              ? 'processing'
              : stored?.latest_terminal_state || null,
          latest_response_type: stored?.latest_response_type || null,
          latest_analysis_goal: stored?.latest_analysis_goal || session.title,
          local_status:
            session.status === 'processing'
              ? 'processing'
              : session.status === 'failed'
                ? 'failed'
                : 'ready',
          local_error: session.error,
        }
      })
    return [...localRows, ...persisted.values()]
  }, [effectiveRuntimeMode, persistedRecent, sessions])

  const activeSession = activeConversationId
    ? sessions[activeConversationId] || null
    : null
  const messages = activeSession?.messages || []
  const sending = activeSession?.sending || false
  const loadingConversation = activeSession?.loadingHistory || false
  const title = activeSession?.title || '新聊天'
  const hasRestoredHistory = Boolean(activeSession?.restored)

  return {
    sessions,
    activeSession,
    messages,
    activeConversationId,
    title,
    error: activeSession?.error || null,
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
    renameReport: renameReportResource,
    bulkRemoveConversations,
    bulkRestoreConversations,
    bulkRemoveReports,
    setSelectedSemanticModel: selectSemanticModel,
    setSelectedReportTemplate,
  }
}
