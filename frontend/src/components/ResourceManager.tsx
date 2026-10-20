import { useTranslation } from 'react-i18next'
import { tr, publicText } from '../i18n'
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
  UserRound,
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
  AccountActions,
} from '../types'
import { CloudAccountSettings } from './CloudAccountSettings'
import { GeneralSettings } from './GeneralSettings'

const SETTINGS_PAGE_SIZE = 20

type SettingsSection =
  | 'general'
  | 'account'
  | 'conversations'
  | 'reports'
  | 'archived'
  | 'models'
  | 'about'

interface ResourceManagerProps {
  account?: AccountActions
  resourceLoaders?: ResourcePageLoaders
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

export interface ResourcePageLoaders {
  conversations: (status: 'active' | 'archived', cursor?: string) => Promise<PageResponse<ConversationSummary>>
  reports: (status: 'active' | 'archived', cursor?: string) => Promise<PageResponse<ConversationReportItem>>
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
              : tr('resources:resourcesCouldNotBeLoadedTryAgainLater'),
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
      if (!ids.length) return
      // A page obtained before this committed mutation is no longer current.
      generationRef.current += 1
      const removed = new Set(ids)
      setState((current) => {
        const items = current.items.filter((item) => !removed.has(keyOf(item)))
        return {
          ...current,
          items,
          loading: false,
          loadingMore: false,
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
    tr('errors:untitledConversation')
  )
}

function reportTitle(item: ConversationReportItem): string {
  return publicText(item.display_title?.trim()) || tr('reports:salesAnalysisReport')
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

export function ResourceManager(props: ResourceManagerProps) {
  useTranslation()
  if (!props.account || props.resourceLoaders) return <LocalResourceManager {...props} />
  const {account, onClose} = props
  return <SettingsFrame onClose={onClose}>
      <CloudAccountSettings account={account} />
  </SettingsFrame>
}

function LocalResourceManager({
  account,
  resourceLoaders,
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
  useTranslation()
  const [section, setSection] = useState<SettingsSection>('general')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | BatchOperationResult | null>(null)
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
      resourceLoaders ? resourceLoaders.conversations('active',cursor) : listRecentConversations(runtimeMode, SETTINGS_PAGE_SIZE, cursor),
    [runtimeMode,resourceLoaders],
  )
  const loadArchivedConversations = useCallback(
    (cursor?: string) =>
      resourceLoaders ? resourceLoaders.conversations('archived',cursor) : listArchivedConversations(runtimeMode, SETTINGS_PAGE_SIZE, cursor),
    [runtimeMode,resourceLoaders],
  )
  const loadActiveReports = useCallback(
    (cursor?: string) =>
      resourceLoaders ? resourceLoaders.reports('active',cursor) : listManagedReports(runtimeMode, 'active', SETTINGS_PAGE_SIZE, cursor),
    [runtimeMode,resourceLoaders],
  )
  const loadArchivedReports = useCallback(
    (cursor?: string) =>
      resourceLoaders ? resourceLoaders.reports('archived',cursor) : listManagedReports(runtimeMode, 'archived', SETTINGS_PAGE_SIZE, cursor),
    [runtimeMode,resourceLoaders],
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

  const showOutcome = (result: BatchOperationResult) => setNotice(result)
  const noticeText=typeof notice==='string' ? publicText(notice) : notice
    ? notice.failed.length===0 ? tr('resources:completedOperations',{p0:notice.succeededIds.length})
      : tr('resources:completedOperationsFailed',{p0:notice.succeededIds.length,p1:notice.failed.length,
        p2:notice.failed.map(item=>tr('resources:failureItem',{id:item.id,reason:publicText(item.reason)}))
          .join(tr('resources:listSeparator'))}) : ''

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
        error instanceof Error ? error.message : tr('resources:theOperationWasNotCompletedTryAgainLater'),
      )
    } finally {
      setBusy(false)
    }
  }

  const renameConversationItem = async (item: ConversationSummary) => {
    const title = window.prompt(tr('resources:enterANewConversationTitle'), conversationTitle(item))?.trim()
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
      setNotice(tr('resources:conversationTitleUpdated'))
    } catch (error) {
      setNotice(error instanceof Error ? error.message : tr('resources:couldNotRenameThisResource'))
    } finally {
      setBusy(false)
    }
  }

  const renameReportItem = async (item: ConversationReportItem) => {
    const title = window.prompt(tr('resources:enterANewReportTitle'), reportTitle(item))?.trim()
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
      setNotice(tr('resources:reportTitleUpdated'))
    } catch (error) {
      setNotice(error instanceof Error ? error.message : tr('resources:couldNotRenameThisResource'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <SettingsFrame onClose={onClose} notice={noticeText}>
        <div className="settings-layout">
          <nav className="settings-nav" aria-label={tr('auth:settingsCategories')}>
            <SettingsNavButton icon={<Settings size={16} />} id="general" label={tr('resources:general')} current={section} onSelect={setSection} />
            {account ? <SettingsNavButton icon={<UserRound size={16} />} id="account" label={tr('auth:account')} current={section} onSelect={setSection} /> : null}
            <SettingsNavButton icon={<MessageSquare size={16} />} id="conversations" label={tr('resources:conversations')} current={section} onSelect={setSection} />
            <SettingsNavButton icon={<BarChart3 size={16} />} id="reports" label={tr('resources:reports')} current={section} onSelect={setSection} />
            <SettingsNavButton icon={<Archive size={16} />} id="archived" label={tr('resources:archived')} current={section} onSelect={setSection} />
            <SettingsNavButton icon={<Database size={16} />} id="models" label={tr('composer:dataModel')} current={section} onSelect={setSection} />
            <SettingsNavButton icon={<Info size={16} />} id="about" label={tr('resources:about')} current={section} onSelect={setSection} />
          </nav>

          <div className="settings-content">
            {section === 'general' ? (
              <GeneralSettings />
            ) : null}
            {section==='account' && account ? <CloudAccountSettings account={account} panel="account" /> : null}

            {section === 'conversations' ? (
              <ResourceSection
                title={tr('resources:conversations')}
                empty={tr('resources:noConversations')}
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
                        void activeReports.reload()
                        void archivedReports.reload()
                      })
                    }}><Archive size={15} />{tr('resources:archiveSelected')}</button>
                    <button className="danger-action" type="button" disabled={busy || activeConversationSelected.size === 0} onClick={() => {
                      const selected = selectedItems(activeConversations.state.items, activeConversationSelected, conversationKey)
                      if (!window.confirm(tr('resources:deleteSelectedConversationsAndTheirReportsThisCannotBe', {p0: selected.length}))) return
                      void run(() => onBulkDeleteConversations(selected), (result) => {
                        activeConversations.removeIds(result.succeededIds)
                        setActiveConversationSelected((current) => removeSucceeded(current, result))
                        setActiveReportSelected(new Set())
                        setArchivedReportSelected(new Set())
                        void activeReports.reload()
                        void archivedReports.reload()
                      })
                    }}><Trash2 size={15} />{tr('resources:deleteSelected')}</button>
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
                title={tr('resources:reports')}
                empty={tr('resources:noReports')}
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
                    }}><Archive size={15} />{tr('resources:archiveSelected')}</button>
                    <button className="danger-action" type="button" disabled={busy || activeReportSelected.size === 0} onClick={() => {
                      const selected = selectedItems(activeReports.state.items, activeReportSelected, reportKey)
                      if (!window.confirm(tr('resources:deleteSelectedReportsTheirConversationsWillRetainADeletion', {p0: selected.length}))) return
                      void run(() => onBulkDeleteReports(selected), (result) => {
                        activeReports.removeIds(result.succeededIds)
                        setActiveReportSelected((current) => removeSucceeded(current, result))
                      })
                    }}><Trash2 size={15} />{tr('resources:deleteSelected')}</button>
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
                  title={tr('resources:archivedConversations')}
                  empty={tr('resources:noArchivedConversations')}
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
                          void activeReports.reload()
                          void archivedReports.reload()
                        })
                      }}><RotateCcw size={15} />{tr('resources:restoreSelected')}</button>
                      <button className="danger-action" type="button" disabled={busy || archivedConversationSelected.size === 0} onClick={() => {
                        const selected = selectedItems(archivedConversations.state.items, archivedConversationSelected, conversationKey)
                        if (!window.confirm(tr('resources:permanentlyDeleteSelectedArchivedConversations', {p0: selected.length}))) return
                        void run(() => onBulkDeleteConversations(selected), (result) => {
                          archivedConversations.removeIds(result.succeededIds)
                          setArchivedConversationSelected((current) => removeSucceeded(current, result))
                          setActiveReportSelected(new Set())
                          setArchivedReportSelected(new Set())
                          void activeReports.reload()
                          void archivedReports.reload()
                        })
                      }}><Trash2 size={15} />{tr('resources:deleteSelected')}</button>
                    </>
                  }
                >
                  {archivedConversations.state.items.map((item) => (
                    <ConversationRow key={item.conversation_id} item={item} selected={archivedConversationSelected.has(item.conversation_id)} onToggle={() => toggleSelection(setArchivedConversationSelected, item.conversation_id)} onRename={() => void renameConversationItem(item)} />
                  ))}
                </ResourceSection>

                <ResourceSection
                  title={tr('resources:archivedReports')}
                  empty={tr('resources:noArchivedReports')}
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
                      }}><RotateCcw size={15} />{tr('resources:restoreSelected')}</button>
                      <button className="danger-action" type="button" disabled={busy || archivedReportSelected.size === 0} onClick={() => {
                        const selected = selectedItems(archivedReports.state.items, archivedReportSelected, reportKey)
                        if (!window.confirm(tr('resources:permanentlyDeleteSelectedArchivedReports', {p0: selected.length}))) return
                        void run(() => onBulkDeleteReports(selected), (result) => {
                          archivedReports.removeIds(result.succeededIds)
                          setArchivedReportSelected((current) => removeSucceeded(current, result))
                        })
                      }}><Trash2 size={15} />{tr('resources:deleteSelected')}</button>
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
              account ? <CloudAccountSettings account={account} panel="data" /> : <SettingsIntro title={tr('composer:dataModel')} text={tr('resources:currentResourceModeDataModelsAreManagedByThe', {p0: tr(runtimeMode==='real'?'resources:modeReal':'resources:modeMock')})} />
            ) : null}
            {section === 'about' ? (
              <SettingsIntro title={tr('resources:about')} text={account ? tr('resources:powerbiagentPowerBiCloudDataAnalysis') : tr('resources:powerbiagentLocalPowerBiDataAnalysis')} />
            ) : null}
          </div>
        </div>
    </SettingsFrame>
  )
}

function SettingsFrame({onClose, notice, children}: {
  onClose: () => void; notice?: string | null; children: ReactNode
}) {
  useTranslation()
  return <div className="resource-manager-backdrop" role="presentation">
    <section className="resource-manager settings-hub" role="dialog" aria-modal="true" aria-labelledby="resource-manager-title">
      <header className="settings-header"><h2 id="resource-manager-title">{tr('resources:settings')}</h2>
        <button type="button" aria-label={tr('resources:closeSettings')} onClick={onClose}><X size={19} /></button></header>
      {notice ? <p className="resource-manager-notice" role="status">{publicText(notice)}</p> : null}
      {children}
    </section>
  </div>
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
  useTranslation()
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
  useTranslation()
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
  useTranslation()
  return (
    <div className="resource-row">
      <input aria-label={tr('resources:selectConversation', {p0: conversationTitle(item)})} type="checkbox" checked={selected} onChange={onToggle} />
      <MessageSquare size={16} />
      <span>{conversationTitle(item)}</span>
      {item.resource_status === 'failed' || item.local_status === 'failed' ? (
        <small className="failed-label">{tr('resources:failed')}</small>
      ) : null}
      <button className="resource-inline-action" type="button" onClick={onRename}>{tr('resources:rename')}</button>
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
  useTranslation()
  return (
    <div className="resource-row">
      <input aria-label={tr('resources:selectReport', {p0: reportTitle(item)})} type="checkbox" checked={selected} onChange={onToggle} />
      <FileText size={16} />
      <span>{reportTitle(item)}</span>
      <button className="resource-inline-action" type="button" onClick={onRename}>{tr('resources:rename')}</button>
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
  useTranslation()
  return (
    <section className="resource-section">
      <div className="resource-section-heading">
        <div><h3>{title}</h3><small>{tr('resources:loadedCount', {count:totalCount, loaded:loadedCount})}</small></div>
        <button type="button" disabled={loadedCount === 0} onClick={onSelectLoaded}>{tr('resources:selectAllLoadedItems')}</button>
      </div>
      <div className="resource-list" role="region" aria-label={tr('resources:resourceList', {p0: title})} aria-busy={loading || loadingMore}>
        {loading ? <p>{tr('resources:loading')}</p> : error ? <p className="resource-error">{publicText(error)}</p> : loadedCount === 0 ? <p>{empty}</p> : children}
        {hasMore ? <button className="resource-load-more" type="button" disabled={loadingMore} onClick={onLoadMore}>{loadingMore ? tr('resources:loadingMore') : tr('resources:loadMore')}</button> : loadedCount > 0 ? <p className="resource-list-end">{tr('resources:allLoaded', {count:totalCount})}</p> : null}
      </div>
      <footer className="resource-toolbar" role="toolbar" aria-label={tr('resources:actions', {p0: title})}>
        <span>{tr('resources:selectionCount', {count:totalCount, selected:selectedCount})}</span>
        <div className="resource-toolbar-actions">{actions}</div>
      </footer>
    </section>
  )
}
