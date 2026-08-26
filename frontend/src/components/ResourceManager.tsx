import {
  Archive,
  BarChart3,
  Database,
  FileText,
  Info,
  MessageSquare,
  RotateCcw,
  Settings,
  Trash2,
  X,
} from 'lucide-react'
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  listArchivedConversations,
  listManagedReports,
  listRecentConversations,
} from '../api/client'
import type {
  BatchOperationResult,
  ConversationReportItem,
  ConversationSummary,
  RuntimeMode,
} from '../types'

const SETTINGS_PAGE_SIZE = 20

type SettingsSection =
  | 'general'
  | 'conversations'
  | 'reports'
  | 'archived'
  | 'models'
  | 'about'

interface ResourceManagerProps {
  runtimeMode: RuntimeMode
  onClose: () => void
  onRenameConversation: (
    item: ConversationSummary,
    title: string,
  ) => Promise<void>
  onBulkDeleteConversations: (
    items: ConversationSummary[],
  ) => Promise<BatchOperationResult>
  onBulkArchiveConversations: (
    items: ConversationSummary[],
  ) => Promise<BatchOperationResult>
  onBulkRestoreConversations: (
    items: ConversationSummary[],
  ) => Promise<BatchOperationResult>
  onBulkDeleteReports: (
    items: ConversationReportItem[],
  ) => Promise<BatchOperationResult>
  onBulkArchiveReports: (
    items: ConversationReportItem[],
  ) => Promise<BatchOperationResult>
  onBulkRestoreReports: (
    items: ConversationReportItem[],
  ) => Promise<BatchOperationResult>
  onRenameReport: (
    report: ConversationReportItem,
    displayTitle: string,
  ) => Promise<void>
}

interface PageResponse<T> {
  items: T[]
  next_cursor: string | null
  total_count: number
}

interface PagedState<T> {
  items: T[]
  nextCursor: string | null
  totalCount: number
  loading: boolean
  loadingMore: boolean
  error: string | null
}

const emptyPage = <T,>(): PagedState<T> => ({
  items: [],
  nextCursor: null,
  totalCount: 0,
  loading: true,
  loadingMore: false,
  error: null,
})

const conversationKey = (item: ConversationSummary) => item.conversation_id
const reportKey = (item: ConversationReportItem) => item.report_id

function usePagedResources<T>(
  loader: (cursor?: string) => Promise<PageResponse<T>>,
  keyOf: (item: T) => string,
) {
  const [state, setState] = useState<PagedState<T>>(emptyPage)
  const generationRef = useRef(0)
  const nextCursorRef = useRef<string | null>(null)

  const load = useCallback(
    async (reset: boolean) => {
      const generation = reset
        ? ++generationRef.current
        : generationRef.current
      const cursor = reset ? undefined : nextCursorRef.current || undefined
      setState((current) => ({
        ...current,
        loading: reset,
        loadingMore: !reset,
        error: null,
      }))
      try {
        const page = await loader(cursor)
        if (generation !== generationRef.current) return
        nextCursorRef.current = page.next_cursor
        setState((current) => {
          const merged = reset
            ? new Map<string, T>()
            : new Map(current.items.map((item) => [keyOf(item), item]))
          page.items.forEach((item) => merged.set(keyOf(item), item))
          return {
            items: [...merged.values()],
            nextCursor: page.next_cursor,
            totalCount: page.total_count,
            loading: false,
            loadingMore: false,
            error: null,
          }
        })
      } catch (error) {
        if (generation !== generationRef.current) return
        setState((current) => ({
          ...current,
          loading: false,
          loadingMore: false,
          error:
            error instanceof Error
              ? error.message
              : '资源加载失败，请稍后重试。',
        }))
      }
    },
    [keyOf, loader],
  )

  useEffect(() => {
    void load(true)
    return () => {
      generationRef.current += 1
    }
  }, [load])

  const removeIds = useCallback(
    (ids: string[]) => {
      const removed = new Set(ids)
      setState((current) => {
        const items = current.items.filter((item) => !removed.has(keyOf(item)))
        return {
          ...current,
          items,
          totalCount: Math.max(
            0,
            current.totalCount - (current.items.length - items.length),
          ),
        }
      })
    },
    [keyOf],
  )

  const updateItem = useCallback(
    (id: string, updater: (item: T) => T) => {
      setState((current) => ({
        ...current,
        items: current.items.map((item) =>
          keyOf(item) === id ? updater(item) : item,
        ),
      }))
    },
    [keyOf],
  )

  return {
    state,
    loadMore: () => load(false),
    reload: () => load(true),
    removeIds,
    updateItem,
  }
}

function conversationTitle(item: ConversationSummary): string {
  return (
    item.title?.trim() ||
    item.latest_analysis_goal?.replace(/^用户提问:\s*/, '').trim() ||
    '未命名对话'
  )
}

function reportTitle(item: ConversationReportItem): string {
  return item.display_title?.trim() || '销售分析报告'
}

function selectedItems<T>(
  items: T[],
  selected: Set<string>,
  keyOf: (item: T) => string,
): T[] {
  return items.filter((item) => selected.has(keyOf(item)))
}

function removeSucceeded(current: Set<string>, result: BatchOperationResult) {
  const next = new Set(current)
  result.succeededIds.forEach((id) => next.delete(id))
  return next
}

export function ResourceManager({
  runtimeMode,
  onClose,
  onRenameConversation,
  onBulkDeleteConversations,
  onBulkArchiveConversations,
  onBulkRestoreConversations,
  onBulkDeleteReports,
  onBulkArchiveReports,
  onBulkRestoreReports,
  onRenameReport,
}: ResourceManagerProps) {
  const [section, setSection] = useState<SettingsSection>('general')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [activeConversationSelected, setActiveConversationSelected] = useState(
    new Set<string>(),
  )
  const [archivedConversationSelected, setArchivedConversationSelected] =
    useState(new Set<string>())
  const [activeReportSelected, setActiveReportSelected] = useState(
    new Set<string>(),
  )
  const [archivedReportSelected, setArchivedReportSelected] = useState(
    new Set<string>(),
  )

  const loadActiveConversations = useCallback(
    (cursor?: string) =>
      listRecentConversations(runtimeMode, SETTINGS_PAGE_SIZE, cursor),
    [runtimeMode],
  )
  const loadArchivedConversations = useCallback(
    (cursor?: string) =>
      listArchivedConversations(runtimeMode, SETTINGS_PAGE_SIZE, cursor),
    [runtimeMode],
  )
  const loadActiveReports = useCallback(
    (cursor?: string) =>
      listManagedReports(runtimeMode, 'active', SETTINGS_PAGE_SIZE, cursor),
    [runtimeMode],
  )
  const loadArchivedReports = useCallback(
    (cursor?: string) =>
      listManagedReports(runtimeMode, 'archived', SETTINGS_PAGE_SIZE, cursor),
    [runtimeMode],
  )

  const activeConversations = usePagedResources(
    loadActiveConversations,
    conversationKey,
  )
  const archivedConversations = usePagedResources(
    loadArchivedConversations,
    conversationKey,
  )
  const activeReports = usePagedResources(loadActiveReports, reportKey)
  const archivedReports = usePagedResources(loadArchivedReports, reportKey)

  const showOutcome = (result: BatchOperationResult) => {
    if (result.failed.length === 0) {
      setNotice(`已完成 ${result.succeededIds.length} 项操作。`)
      return
    }
    setNotice(
      `已完成 ${result.succeededIds.length} 项，${result.failed.length} 项失败：${result.failed
        .map((item) => `${item.id}（${item.reason}）`)
        .join('；')}`,
    )
  }

  const run = async (
    operation: () => Promise<BatchOperationResult>,
    onSuccess: (result: BatchOperationResult) => void,
  ) => {
    setBusy(true)
    setNotice(null)
    try {
      const result = await operation()
      onSuccess(result)
      showOutcome(result)
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : '操作未完成，请稍后重试。',
      )
    } finally {
      setBusy(false)
    }
  }

  const renameConversationItem = async (item: ConversationSummary) => {
    const title = window.prompt('输入新的对话标题', conversationTitle(item))?.trim()
    if (!title) return
    setBusy(true)
    try {
      await onRenameConversation(item, title)
      activeConversations.updateItem(item.conversation_id, (current) => ({
        ...current,
        title,
      }))
      archivedConversations.updateItem(item.conversation_id, (current) => ({
        ...current,
        title,
      }))
      setNotice('对话标题已更新。')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '重命名失败。')
    } finally {
      setBusy(false)
    }
  }

  const renameReportItem = async (item: ConversationReportItem) => {
    const title = window.prompt('输入新的报表标题', reportTitle(item))?.trim()
    if (!title) return
    setBusy(true)
    try {
      await onRenameReport(item, title)
      activeReports.updateItem(item.report_id, (current) => ({
        ...current,
        display_title: title,
      }))
      archivedReports.updateItem(item.report_id, (current) => ({
        ...current,
        display_title: title,
      }))
      setNotice('报表标题已更新。')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '重命名失败。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="resource-manager-backdrop" role="presentation">
      <section
        className="resource-manager settings-hub"
        role="dialog"
        aria-modal="true"
        aria-labelledby="resource-manager-title"
      >
        <header className="settings-header">
          <div>
            <span className="resource-manager-eyebrow">用户设置</span>
            <h2 id="resource-manager-title">设置</h2>
            <p>完整历史按页加载；大批量操作会自动安全分组执行。</p>
          </div>
          <button type="button" aria-label="关闭设置" onClick={onClose}>
            <X size={19} />
          </button>
        </header>

        {notice ? (
          <p className="resource-manager-notice" role="status">
            {notice}
          </p>
        ) : null}

        <div className="settings-layout">
          <nav className="settings-nav" aria-label="设置分类">
            <SettingsNavButton icon={<Settings size={16} />} id="general" label="常规" current={section} onSelect={setSection} />
            <SettingsNavButton icon={<MessageSquare size={16} />} id="conversations" label="对话管理" current={section} onSelect={setSection} />
            <SettingsNavButton icon={<BarChart3 size={16} />} id="reports" label="报表管理" current={section} onSelect={setSection} />
            <SettingsNavButton icon={<Archive size={16} />} id="archived" label="已归档" current={section} onSelect={setSection} />
            <SettingsNavButton icon={<Database size={16} />} id="models" label="数据模型" current={section} onSelect={setSection} />
            <SettingsNavButton icon={<Info size={16} />} id="about" label="关于" current={section} onSelect={setSection} />
          </nav>

          <div className="settings-content">
            {section === 'general' ? (
              <SettingsIntro title="常规" text="资源管理使用独立分页，不影响左侧栏的最近记录。" />
            ) : null}

            {section === 'conversations' ? (
              <ResourceSection
                title="对话管理"
                empty="暂无对话"
                selectedCount={activeConversationSelected.size}
                loadedCount={activeConversations.state.items.length}
                totalCount={activeConversations.state.totalCount}
                loading={activeConversations.state.loading}
                loadingMore={activeConversations.state.loadingMore}
                error={activeConversations.state.error}
                hasMore={Boolean(activeConversations.state.nextCursor)}
                onLoadMore={activeConversations.loadMore}
                onSelectLoaded={() => setActiveConversationSelected(
                  new Set(activeConversations.state.items.map(conversationKey)),
                )}
                actions={
                  <>
                    <button type="button" disabled={busy || activeConversationSelected.size === 0} onClick={() => {
                      const selected = selectedItems(activeConversations.state.items, activeConversationSelected, conversationKey)
                      void run(() => onBulkArchiveConversations(selected), (result) => {
                        activeConversations.removeIds(result.succeededIds)
                        setActiveConversationSelected((current) => removeSucceeded(current, result))
                        void archivedConversations.reload()
                      })
                    }}><Archive size={15} />批量归档</button>
                    <button className="danger-action" type="button" disabled={busy || activeConversationSelected.size === 0} onClick={() => {
                      const selected = selectedItems(activeConversations.state.items, activeConversationSelected, conversationKey)
                      if (!window.confirm(`删除选中的 ${selected.length} 个对话及其关联报表？此操作不可撤销。`)) return
                      void run(() => onBulkDeleteConversations(selected), (result) => {
                        activeConversations.removeIds(result.succeededIds)
                        setActiveConversationSelected((current) => removeSucceeded(current, result))
                        setActiveReportSelected(new Set())
                        setArchivedReportSelected(new Set())
                        void activeReports.reload()
                        void archivedReports.reload()
                      })
                    }}><Trash2 size={15} />批量删除</button>
                  </>
                }
              >
                {activeConversations.state.items.map((item) => (
                  <ConversationRow key={item.conversation_id} item={item} selected={activeConversationSelected.has(item.conversation_id)} onToggle={() => toggleSelection(setActiveConversationSelected, item.conversation_id)} onRename={() => void renameConversationItem(item)} />
                ))}
              </ResourceSection>
            ) : null}

            {section === 'reports' ? (
              <ResourceSection
                title="报表管理"
                empty="暂无报表"
                selectedCount={activeReportSelected.size}
                loadedCount={activeReports.state.items.length}
                totalCount={activeReports.state.totalCount}
                loading={activeReports.state.loading}
                loadingMore={activeReports.state.loadingMore}
                error={activeReports.state.error}
                hasMore={Boolean(activeReports.state.nextCursor)}
                onLoadMore={activeReports.loadMore}
                onSelectLoaded={() => setActiveReportSelected(new Set(activeReports.state.items.map(reportKey)))}
                actions={
                  <>
                    <button type="button" disabled={busy || activeReportSelected.size === 0} onClick={() => {
                      const selected = selectedItems(activeReports.state.items, activeReportSelected, reportKey)
                      void run(() => onBulkArchiveReports(selected), (result) => {
                        activeReports.removeIds(result.succeededIds)
                        setActiveReportSelected((current) => removeSucceeded(current, result))
                        void archivedReports.reload()
                      })
                    }}><Archive size={15} />批量归档</button>
                    <button className="danger-action" type="button" disabled={busy || activeReportSelected.size === 0} onClick={() => {
                      const selected = selectedItems(activeReports.state.items, activeReportSelected, reportKey)
                      if (!window.confirm(`删除选中的 ${selected.length} 个报表？所属对话会保留删除记录。`)) return
                      void run(() => onBulkDeleteReports(selected), (result) => {
                        activeReports.removeIds(result.succeededIds)
                        setActiveReportSelected((current) => removeSucceeded(current, result))
                      })
                    }}><Trash2 size={15} />批量删除</button>
                  </>
                }
              >
                {activeReports.state.items.map((item) => (
                  <ReportRow key={item.report_id} item={item} selected={activeReportSelected.has(item.report_id)} onToggle={() => toggleSelection(setActiveReportSelected, item.report_id)} onRename={() => void renameReportItem(item)} />
                ))}
              </ResourceSection>
            ) : null}

            {section === 'archived' ? (
              <div className="resource-manager-sections">
                <ResourceSection
                  title="已归档对话"
                  empty="暂无已归档对话"
                  selectedCount={archivedConversationSelected.size}
                  loadedCount={archivedConversations.state.items.length}
                  totalCount={archivedConversations.state.totalCount}
                  loading={archivedConversations.state.loading}
                  loadingMore={archivedConversations.state.loadingMore}
                  error={archivedConversations.state.error}
                  hasMore={Boolean(archivedConversations.state.nextCursor)}
                  onLoadMore={archivedConversations.loadMore}
                  onSelectLoaded={() => setArchivedConversationSelected(new Set(archivedConversations.state.items.map(conversationKey)))}
                  actions={
                    <>
                      <button type="button" disabled={busy || archivedConversationSelected.size === 0} onClick={() => {
                        const selected = selectedItems(archivedConversations.state.items, archivedConversationSelected, conversationKey)
                        void run(() => onBulkRestoreConversations(selected), (result) => {
                          archivedConversations.removeIds(result.succeededIds)
                          setArchivedConversationSelected((current) => removeSucceeded(current, result))
                          void activeConversations.reload()
                        })
                      }}><RotateCcw size={15} />批量恢复</button>
                      <button className="danger-action" type="button" disabled={busy || archivedConversationSelected.size === 0} onClick={() => {
                        const selected = selectedItems(archivedConversations.state.items, archivedConversationSelected, conversationKey)
                        if (!window.confirm(`永久删除选中的 ${selected.length} 个已归档对话？`)) return
                        void run(() => onBulkDeleteConversations(selected), (result) => {
                          archivedConversations.removeIds(result.succeededIds)
                          setArchivedConversationSelected((current) => removeSucceeded(current, result))
                          setActiveReportSelected(new Set())
                          setArchivedReportSelected(new Set())
                          void activeReports.reload()
                          void archivedReports.reload()
                        })
                      }}><Trash2 size={15} />批量删除</button>
                    </>
                  }
                >
                  {archivedConversations.state.items.map((item) => (
                    <ConversationRow key={item.conversation_id} item={item} selected={archivedConversationSelected.has(item.conversation_id)} onToggle={() => toggleSelection(setArchivedConversationSelected, item.conversation_id)} onRename={() => void renameConversationItem(item)} />
                  ))}
                </ResourceSection>

                <ResourceSection
                  title="已归档报表"
                  empty="暂无已归档报表"
                  selectedCount={archivedReportSelected.size}
                  loadedCount={archivedReports.state.items.length}
                  totalCount={archivedReports.state.totalCount}
                  loading={archivedReports.state.loading}
                  loadingMore={archivedReports.state.loadingMore}
                  error={archivedReports.state.error}
                  hasMore={Boolean(archivedReports.state.nextCursor)}
                  onLoadMore={archivedReports.loadMore}
                  onSelectLoaded={() => setArchivedReportSelected(new Set(archivedReports.state.items.map(reportKey)))}
                  actions={
                    <>
                      <button type="button" disabled={busy || archivedReportSelected.size === 0} onClick={() => {
                        const selected = selectedItems(archivedReports.state.items, archivedReportSelected, reportKey)
                        void run(() => onBulkRestoreReports(selected), (result) => {
                          archivedReports.removeIds(result.succeededIds)
                          setArchivedReportSelected((current) => removeSucceeded(current, result))
                          void activeReports.reload()
                        })
                      }}><RotateCcw size={15} />批量恢复</button>
                      <button className="danger-action" type="button" disabled={busy || archivedReportSelected.size === 0} onClick={() => {
                        const selected = selectedItems(archivedReports.state.items, archivedReportSelected, reportKey)
                        if (!window.confirm(`永久删除选中的 ${selected.length} 个已归档报表？`)) return
                        void run(() => onBulkDeleteReports(selected), (result) => {
                          archivedReports.removeIds(result.succeededIds)
                          setArchivedReportSelected((current) => removeSucceeded(current, result))
                        })
                      }}><Trash2 size={15} />批量删除</button>
                    </>
                  }
                >
                  {archivedReports.state.items.map((item) => (
                    <ReportRow key={item.report_id} item={item} selected={archivedReportSelected.has(item.report_id)} onToggle={() => toggleSelection(setArchivedReportSelected, item.report_id)} onRename={() => void renameReportItem(item)} />
                  ))}
                </ResourceSection>
              </div>
            ) : null}

            {section === 'models' ? (
              <SettingsIntro title="数据模型" text={`当前资源 namespace：${runtimeMode}。数据模型仍由后端安全发现接口管理。`} />
            ) : null}
            {section === 'about' ? (
              <SettingsIntro title="关于" text="PowerBIAgent M5.4.1 — 本地 Power BI 数据分析 Agent。" />
            ) : null}
          </div>
        </div>
      </section>
    </div>
  )
}

function toggleSelection(
  setter: React.Dispatch<React.SetStateAction<Set<string>>>,
  id: string,
) {
  setter((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })
}

function SettingsNavButton({
  icon,
  id,
  label,
  current,
  onSelect,
}: {
  icon: ReactNode
  id: SettingsSection
  label: string
  current: SettingsSection
  onSelect: (section: SettingsSection) => void
}) {
  return (
    <button
      className={current === id ? 'is-active' : ''}
      type="button"
      aria-current={current === id ? 'page' : undefined}
      onClick={() => onSelect(id)}
    >
      {icon}<span>{label}</span>
    </button>
  )
}

function SettingsIntro({ title, text }: { title: string; text: string }) {
  return (
    <section className="settings-intro">
      <h3>{title}</h3>
      <p>{text}</p>
    </section>
  )
}

function ConversationRow({
  item,
  selected,
  onToggle,
  onRename,
}: {
  item: ConversationSummary
  selected: boolean
  onToggle: () => void
  onRename: () => void
}) {
  return (
    <div className="resource-row">
      <input aria-label={`选择对话：${conversationTitle(item)}`} type="checkbox" checked={selected} onChange={onToggle} />
      <MessageSquare size={16} />
      <span>{conversationTitle(item)}</span>
      {item.resource_status === 'failed' || item.local_status === 'failed' ? (
        <small className="failed-label">失败</small>
      ) : null}
      <button className="resource-inline-action" type="button" onClick={onRename}>重命名</button>
    </div>
  )
}

function ReportRow({
  item,
  selected,
  onToggle,
  onRename,
}: {
  item: ConversationReportItem
  selected: boolean
  onToggle: () => void
  onRename: () => void
}) {
  return (
    <div className="resource-row">
      <input aria-label={`选择报表：${reportTitle(item)}`} type="checkbox" checked={selected} onChange={onToggle} />
      <FileText size={16} />
      <span>{reportTitle(item)}</span>
      <button className="resource-inline-action" type="button" onClick={onRename}>重命名</button>
    </div>
  )
}

function ResourceSection({
  title,
  empty,
  selectedCount,
  loadedCount,
  totalCount,
  loading,
  loadingMore,
  error,
  hasMore,
  onLoadMore,
  onSelectLoaded,
  actions,
  children,
}: {
  title: string
  empty: string
  selectedCount: number
  loadedCount: number
  totalCount: number
  loading: boolean
  loadingMore: boolean
  error: string | null
  hasMore: boolean
  onLoadMore: () => void
  onSelectLoaded: () => void
  actions: ReactNode
  children: ReactNode
}) {
  return (
    <section className="resource-section">
      <div className="resource-section-heading">
        <div><h3>{title}</h3><small>共 {totalCount} 项 · 已加载 {loadedCount} 项</small></div>
        <button type="button" disabled={loadedCount === 0} onClick={onSelectLoaded}>全选当前已加载</button>
      </div>
      <div className="resource-list" role="region" aria-label={`${title}资源列表`} aria-busy={loading || loadingMore}>
        {loading ? <p>正在加载…</p> : error ? <p className="resource-error">{error}</p> : loadedCount === 0 ? <p>{empty}</p> : children}
        {hasMore ? <button className="resource-load-more" type="button" disabled={loadingMore} onClick={onLoadMore}>{loadingMore ? '正在加载更多…' : '加载更多'}</button> : loadedCount > 0 ? <p className="resource-list-end">已加载全部 {totalCount} 项</p> : null}
      </div>
      <footer className="resource-toolbar" role="toolbar" aria-label={`${title}操作栏`}>
        <span>已选择 {selectedCount} / 共 {totalCount} 项</span>
        <div className="resource-toolbar-actions">{actions}</div>
      </footer>
    </section>
  )
}
