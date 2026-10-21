import { useTranslation } from 'react-i18next'
import { tr, publicText, reportReference } from '../i18n'
import {
  Archive,
  BarChart3,
  ChevronDown,
  FileText,
  Folder,
  LoaderCircle,
  LogOut,
  MessageSquare,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Settings,
  Trash2,
  UserRound,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { isUsableReport } from '../api/adapters'
import type {
  BatchOperationResult,
  ConversationReportItem,
  ConversationSummary,
  RuntimeMode,
  AccountActions,
} from '../types'
import { FloatingActionMenu } from './FloatingActionMenu'
import { ResourceManager, type ResourcePageLoaders } from './ResourceManager'

type ActionMenu =
  | { anchor: HTMLButtonElement; id: string; type: 'conversation' }
  | { anchor: HTMLButtonElement; id: string; type: 'report' }

interface SidebarProps {
  resourceLoaders?: ResourcePageLoaders
  cloudExecutionReady?: boolean
  account?: AccountActions
  collapsed: boolean
  activeConversationId: string | null
  runtimeMode: RuntimeMode
  conversations: ConversationSummary[]
  reports: ConversationReportItem[]
  error: string | null
  onToggle: () => void
  onNewChat: () => void
  onOpenConversation: (conversation: ConversationSummary) => void
  onSearch: (query: string) => Promise<ConversationSummary[]>
  onRename: (conversation: ConversationSummary, title: string) => Promise<void>
  onArchive: (conversation: ConversationSummary) => Promise<void>
  onRestore: (conversation: ConversationSummary) => Promise<void>
  onDelete: (conversation: ConversationSummary) => Promise<void>
  onDeleteReport: (report: ConversationReportItem) => Promise<void>
  onArchiveReport: (report: ConversationReportItem) => Promise<void>
  onRenameReport: (report: ConversationReportItem, title: string) => Promise<void>
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
}

function displayTitle(conversation: ConversationSummary): string {
  return conversation.title?.trim() || conversation.latest_analysis_goal?.replace(/^用户提问:\s*/, '').trim() || tr('errors:untitledConversation')
}

type ConversationResourceStatus = 'ready' | 'processing' | 'failed'

function SidebarLeadingIcon({ status }: { status: ConversationResourceStatus }) {
  useTranslation()
  return (
    <span
      className="conversation-item-icon"
      data-resource-status={status}
      aria-hidden="true"
    >
      {status === 'processing' ? (
        <LoaderCircle className="pending-spinner" size={16} />
      ) : (
        <MessageSquare size={16} />
      )}
    </span>
  )
}

export function Sidebar({
  resourceLoaders,
  cloudExecutionReady=false,
  account,
  collapsed,
  activeConversationId,
  runtimeMode,
  conversations,
  reports,
  error,
  onToggle,
  onNewChat,
  onOpenConversation,
  onSearch,
  onRename,
  onArchive,
  onRestore,
  onDelete,
  onDeleteReport,
  onArchiveReport,
  onRenameReport,
  onBulkDeleteConversations,
  onBulkArchiveConversations,
  onBulkRestoreConversations,
  onBulkDeleteReports,
  onBulkArchiveReports,
  onBulkRestoreReports,
}: SidebarProps) {
  useTranslation()
  const [searchOpen, setSearchOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<ConversationSummary[] | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [actionMenu, setActionMenu] = useState<ActionMenu | null>(null)
  const [editingConversationId, setEditingConversationId] = useState<string | null>(null)
  const [draftTitle, setDraftTitle] = useState('')
  const [managingConversationId, setManagingConversationId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [managingReportId, setManagingReportId] = useState<string | null>(null)
  const [recentOpen, setRecentOpen] = useState(true)
  const [reportsOpen, setReportsOpen] = useState(true)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [resourceManagerOpen, setResourceManagerOpen] = useState(false)
  const accountActionsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!userMenuOpen) return
    const actions = accountActionsRef.current
    actions?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
    return () => actions?.querySelector<HTMLButtonElement>('.account-card')?.focus()
  }, [userMenuOpen])

  useEffect(() => {
    const closeMenus = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setActionMenu(null)
      setEditingConversationId(null)
      setSearchOpen(false)
      setUserMenuOpen(false)
      setResourceManagerOpen(false)
    }
    const closeActionMenu = (event: MouseEvent) => {
      const target = event.target
      if (
        target instanceof Element &&
        !target.closest('[data-account-actions]')
      ) {
        setUserMenuOpen(false)
      }
    }
    document.addEventListener('keydown', closeMenus)
    document.addEventListener('mousedown', closeActionMenu)
    return () => {
      document.removeEventListener('keydown', closeMenus)
      document.removeEventListener('mousedown', closeActionMenu)
    }
  }, [])

  const runSearch = async () => {
    const normalized = query.trim()
    if (!normalized || searching) return
    setSearching(true)
    setSearchError(null)
    try {
      setSearchResults(await onSearch(normalized))
    } catch (searchFailure) {
      setSearchResults([])
      setSearchError(searchFailure instanceof Error ? searchFailure.message : tr('sidebar:searchIsUnavailableTryAgainLater'))
    } finally {
      setSearching(false)
    }
  }

  const manage = async (
    conversation: ConversationSummary,
    action: () => Promise<void>,
  ) => {
    setManagingConversationId(conversation.conversation_id)
    setActionError(null)
    try {
      await action()
      setActionMenu(null)
      setEditingConversationId(null)
    } catch (failure) {
      setActionError(failure instanceof Error ? failure.message : tr('resources:theOperationWasNotCompletedTryAgainLater'))
    } finally {
      setManagingConversationId(null)
    }
  }

  const manageReport = async (
    report: ConversationReportItem,
    action: () => Promise<void>,
  ) => {
    setManagingReportId(report.report_id)
    setActionError(null)
    try {
      await action()
      setActionMenu(null)
    } catch (failure) {
      setActionError(
        failure instanceof Error ? failure.message : tr('sidebar:theReportOperationWasNotCompletedTryAgainLater'),
      )
    } finally {
      setManagingReportId(null)
    }
  }

  const conversationRows = (
    items: ConversationSummary[],
    archived = false,
  ) => items.map((conversation) => {
    const title = displayTitle(conversation)
    const isEditing = editingConversationId === conversation.conversation_id
    const busy = managingConversationId === conversation.conversation_id
    const resourceStatus =
      conversation.local_status ?? conversation.resource_status ?? 'ready'
    return (
      <div className="sidebar-item-row" data-conversation-actions key={conversation.conversation_id}>
        {isEditing ? (
          <form
            className="sidebar-rename-form"
            onSubmit={(event) => {
              event.preventDefault()
              if (draftTitle.trim()) void manage(conversation, () => onRename(conversation, draftTitle.trim()))
            }}
          >
            <input autoFocus maxLength={80} aria-label={tr('sidebar:newConversationTitle')} value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} />
            <button type="submit" disabled={!draftTitle.trim() || busy}>{tr('sidebar:save')}</button>
          </form>
        ) : (
          <>
            <button
              className={`sidebar-item conversation-item-content ${conversation.conversation_id === activeConversationId ? 'is-current' : ''}`}
              type="button"
              title={title}
              onClick={() => onOpenConversation(conversation)}
            >
              <SidebarLeadingIcon status={resourceStatus} />
              <span className="conversation-item-title">{title}</span>
              {resourceStatus === 'processing' ? (
                <small className="pending-label">{tr('chat:analyzing')}</small>
              ) : null}
              {resourceStatus === 'failed' ? (
                <small className="failed-label">{tr('resources:failed')}</small>
              ) : null}
            </button>
            {!account || resourceLoaders ? <button
              className="conversation-actions-trigger"
              type="button"
              aria-label={tr('sidebar:manageConversation', {p0: title})}
              aria-haspopup="menu"
              aria-expanded={actionMenu?.type === 'conversation' && actionMenu.id === conversation.conversation_id}
              onClick={(event) => {
                const anchor = event.currentTarget
                setActionMenu((current) => (
                  current?.type === 'conversation' && current.id === conversation.conversation_id
                    ? null
                    : { anchor, id: conversation.conversation_id, type: 'conversation' }
                ))
              }}
            >
              <MoreHorizontal size={17} />
            </button> : null}
          </>
        )}
        {actionMenu?.type === 'conversation' && actionMenu.id === conversation.conversation_id && !isEditing ? (
          <FloatingActionMenu anchor={actionMenu.anchor} ariaLabel={tr('sidebar:conversationActions', {p0: title})} onClose={() => setActionMenu(null)}>
            {resourceStatus !== 'processing' ? <button type="button" role="menuitem" onClick={() => { setDraftTitle(title); setEditingConversationId(conversation.conversation_id); setActionMenu(null) }}><Pencil size={15} />{tr('resources:rename')}</button> : null}
            {archived ? (
              <button type="button" role="menuitem" disabled={busy} onClick={() => void manage(conversation, () => onRestore(conversation))}><RotateCcw size={15} />{tr('sidebar:restore')}</button>
            ) : resourceStatus !== 'processing' ? (
              <button type="button" role="menuitem" disabled={busy} onClick={() => void manage(conversation, () => onArchive(conversation))}><Archive size={15} />{tr('sidebar:archive')}</button>
            ) : null}
            <button className="danger-action" type="button" role="menuitem" disabled={busy || resourceStatus === 'processing'} onClick={() => {
              if (window.confirm(tr('sidebar:deleteAndItsReportsThisCannotBeUndone', {p0: title}))) void manage(conversation, () => onDelete(conversation))
            }}><Trash2 size={15} />{tr('sidebar:delete')}</button>
          </FloatingActionMenu>
        ) : null}
      </div>
    )
  })

  return (
    <>
    <aside className={`sidebar ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <div className="sidebar-brand-row">
        <div className="brand-mark" title="PowerBIAgent"><BarChart3 size={20} strokeWidth={1.8} /><strong>PowerBIAgent</strong></div>
        <button className="plain-icon-button" type="button" onClick={onToggle} aria-label={collapsed ? tr('sidebar:expandSidebar') : tr('sidebar:collapseSidebar')}>
          {collapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}
        </button>
      </div>

      {!account || cloudExecutionReady || resourceLoaders ? <nav className="sidebar-primary" aria-label={tr('sidebar:mainNavigation')}>
        {!account || cloudExecutionReady ? <button type="button" onClick={onNewChat} title={tr('sidebar:newChat')}><Plus size={20} /><span>{tr('sidebar:newChat')}</span></button> : null}
        {!account || resourceLoaders ? <button type="button" onClick={() => { if (collapsed) onToggle(); setSearchOpen(true) }} title={tr('sidebar:searchChats')}><Search size={19} /><span>{tr('sidebar:searchChats')}</span></button> : null}
      </nav> : null}

      {!collapsed && searchOpen && (!account || cloudExecutionReady || resourceLoaders) ? (
        <section className="sidebar-search" aria-label={tr('sidebar:searchChats')}>
          <div className="sidebar-search-heading"><strong>{tr('sidebar:searchChats')}</strong><button type="button" aria-label={tr('sidebar:closeSearch')} onClick={() => setSearchOpen(false)}><X size={16} /></button></div>
          <form onSubmit={(event) => { event.preventDefault(); void runSearch() }}>
            <input value={query} maxLength={200} autoFocus placeholder={tr('sidebar:searchTitlesQuestionsOrAnswers')} aria-label={tr('sidebar:searchTitlesQuestionsOrAnswers')} onChange={(event) => setQuery(event.target.value)} />
            <button type="submit" aria-label={tr('sidebar:search')} disabled={!query.trim() || searching}><Search size={16} /></button>
          </form>
          {searching ? <p className="sidebar-state">{tr('sidebar:searching')}</p> : null}
          {searchError ? <p className="sidebar-state sidebar-state-error">{publicText(searchError)}</p> : null}
          {searchResults?.length === 0 && !searchError ? <p className="sidebar-state">{tr('sidebar:noMatchingConversations')}</p> : null}
          {searchResults ? conversationRows(searchResults) : null}
        </section>
      ) : null}

      {!account || cloudExecutionReady || resourceLoaders ? <div className="sidebar-scroll">
        <section className="sidebar-section project-section"><span className="sidebar-label">{tr('sidebar:projects')}</span><div className="project-card" title={tr('sidebar:powerBiSalesAnalysis')}><Folder size={18} /><span>{tr('sidebar:powerBiSalesAnalysis')}</span></div></section>
        <section className="sidebar-section collapsible-section">
          <button className="sidebar-section-toggle" type="button" aria-expanded={reportsOpen} onClick={() => setReportsOpen((open) => !open)}><span>{tr('sidebar:recentReports')}</span><ChevronDown className={reportsOpen ? 'is-open' : ''} size={15} /></button>
          {reportsOpen && reports.length === 0 ? <p className="sidebar-state">{tr('sidebar:noRecentReports')}</p> : reportsOpen ? reports.map((report) => isUsableReport(report) ? (
            <div className="sidebar-item-row" data-report-actions key={report.report_id}>
              <a className="sidebar-item" href={reportReference(report.view_reference)} target="_blank" rel="noreferrer" title={tr('sidebar:view', {p0: report.display_title || tr('reports:salesAnalysisReport')})}><FileText size={17} /><span>{publicText(report.display_title) || tr('reports:salesAnalysisReport')}</span></a>
              {!account || resourceLoaders ? <button className="conversation-actions-trigger" type="button" aria-label={tr('sidebar:manageReport', {p0: report.display_title || tr('reports:salesAnalysisReport')})} aria-haspopup="menu" aria-expanded={actionMenu?.type === 'report' && actionMenu.id === report.report_id} onClick={(event) => {
                const anchor = event.currentTarget
                setActionMenu((current) => (
                  current?.type === 'report' && current.id === report.report_id
                    ? null
                    : { anchor, id: report.report_id, type: 'report' }
                ))
              }}><MoreHorizontal size={17} /></button> : null}
              {actionMenu?.type === 'report' && actionMenu.id === report.report_id ? (
                <FloatingActionMenu anchor={actionMenu.anchor} ariaLabel={tr('sidebar:reportActions', {p0: report.display_title || tr('reports:salesAnalysisReport')})} onClose={() => setActionMenu(null)}>
                  <button type="button" role="menuitem" disabled={managingReportId === report.report_id} onClick={() => {
                    const title = window.prompt(tr('resources:enterANewReportTitle'), report.display_title || tr('reports:salesAnalysisReport'))?.trim()
                    if (title) void manageReport(report, () => onRenameReport(report, title))
                  }}><Pencil size={15} />{tr('resources:rename')}</button>
                  <button type="button" role="menuitem" disabled={managingReportId === report.report_id} onClick={() => {
                    void manageReport(report, () => onArchiveReport(report))
                  }}><Archive size={15} />{tr('sidebar:archive')}</button>
                  <button className="danger-action" type="button" role="menuitem" disabled={managingReportId === report.report_id} onClick={() => {
                    if (window.confirm(tr('sidebar:deleteThisCannotBeUndoneTheConversationWillBe', {p0: report.display_title || tr('reports:salesAnalysisReport')}))) void manageReport(report, () => onDeleteReport(report))
                  }}><Trash2 size={15} />{tr('sidebar:deleteReport')}</button>
                </FloatingActionMenu>
              ) : null}
            </div>
          ) : null) : null}
        </section>
        <section className="sidebar-section collapsible-section recent-section">
          <button className="sidebar-section-toggle" type="button" aria-expanded={recentOpen} onClick={() => setRecentOpen((open) => !open)}><span>{tr('sidebar:recentConversations')}</span><ChevronDown className={recentOpen ? 'is-open' : ''} size={15} /></button>
          {recentOpen && error ? <p className="sidebar-state">{publicText(error)}</p> : null}
          {recentOpen && !error && conversations.length === 0 ? <p className="sidebar-state">{tr('sidebar:noRecentConversations')}</p> : null}
          {recentOpen ? <div className="recent-conversation-list">{conversationRows(conversations)}</div> : null}
          {actionError ? <p className="sidebar-state sidebar-state-error" role="alert">{publicText(actionError)}</p> : null}
        </section>
      </div> : <div className="sidebar-scroll" />}
      <div className="account-actions" data-account-actions ref={accountActionsRef}>
        {account && !account.session.authenticated ? <button className="account-settings-trigger" type="button" aria-label={tr('resources:settings')} onClick={()=>setResourceManagerOpen(true)}><Settings size={17} /><span>{tr('resources:settings')}</span></button> : null}
        {userMenuOpen && !collapsed ? <div className="account-menu" role="menu" aria-label={tr('sidebar:userMenu')}>
          <button type="button" role="menuitem" onClick={() => { setResourceManagerOpen(true); setUserMenuOpen(false) }}><Settings size={16} />{tr('resources:settings')}</button>
          {account?.session.authenticated ? <button type="button" role="menuitem" onClick={() => void account.logout()}><LogOut size={16} />{tr('auth:signOut')}</button> : null}
        </div> : null}
        {account && !account.session.authenticated ?
          <button className="account-card" type="button" aria-label={tr('sidebar:signInWithMicrosoft')} title={tr('sidebar:signInWithMicrosoft')} disabled={['AUTHENTICATING', 'SESSION_ESTABLISHING'].includes(account.state)} onClick={account.login}><span className="account-avatar"><UserRound size={16} /></span><span className="account-copy"><strong>{tr('sidebar:signInWithMicrosoft')}</strong></span></button>
          : <button className="account-card" type="button" title={account?.session.display_name || tr('sidebar:powerbiagentUser')} aria-label={account?.session.display_name || tr('sidebar:powerbiagentUser')} aria-haspopup="menu" aria-expanded={userMenuOpen} onClick={() => { if (collapsed) onToggle(); setUserMenuOpen((open) => !open) }}><span className="account-avatar"><UserRound size={16} /></span><span className="account-copy"><strong>{account?.session.display_name || 'PowerBIAgent'}</strong><small>{account ? account.session.preferred_username : tr('sidebar:internalUser')}</small></span></button>}
      </div>
    </aside>
    {resourceManagerOpen ? <ResourceManager account={account} resourceLoaders={resourceLoaders} runtimeMode={runtimeMode} onClose={() => setResourceManagerOpen(false)} onRenameConversation={onRename} onBulkDeleteConversations={onBulkDeleteConversations} onBulkArchiveConversations={onBulkArchiveConversations} onBulkRestoreConversations={onBulkRestoreConversations} onBulkDeleteReports={onBulkDeleteReports} onBulkArchiveReports={onBulkArchiveReports} onBulkRestoreReports={onBulkRestoreReports} onRenameReport={onRenameReport} /> : null}
    </>
  )
}
