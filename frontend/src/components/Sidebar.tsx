import {
  Archive,
  BarChart3,
  ChevronDown,
  FileText,
  Folder,
  LoaderCircle,
  MessageSquare,
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
import { useEffect, useState } from 'react'
import { isUsableReport } from '../api/adapters'
import type {
  BatchOperationResult,
  ConversationReportItem,
  ConversationSummary,
  RuntimeMode,
} from '../types'
import { ResourceManager } from './ResourceManager'
import { FloatingActionMenu } from './FloatingActionMenu'

interface SidebarProps {
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
  return conversation.title?.trim() || conversation.latest_analysis_goal?.replace(/^用户提问:\s*/, '').trim() || '未命名对话'
}

export function Sidebar({
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
  const [searchOpen, setSearchOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<ConversationSummary[] | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [actionConversationId, setActionConversationId] = useState<string | null>(null)
  const [editingConversationId, setEditingConversationId] = useState<string | null>(null)
  const [draftTitle, setDraftTitle] = useState('')
  const [managingConversationId, setManagingConversationId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionReportId, setActionReportId] = useState<string | null>(null)
  const [managingReportId, setManagingReportId] = useState<string | null>(null)
  const [recentOpen, setRecentOpen] = useState(true)
  const [reportsOpen, setReportsOpen] = useState(true)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [resourceManagerOpen, setResourceManagerOpen] = useState(false)

  useEffect(() => {
    const closeMenus = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
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
      setSearchError(searchFailure instanceof Error ? searchFailure.message : '搜索暂时不可用，请稍后重试。')
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
      setActionConversationId(null)
      setEditingConversationId(null)
    } catch (failure) {
      setActionError(failure instanceof Error ? failure.message : '操作未完成，请稍后重试。')
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
      setActionReportId(null)
    } catch (failure) {
      setActionError(
        failure instanceof Error ? failure.message : '报表操作未完成，请稍后重试。',
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
            <input autoFocus maxLength={80} aria-label="新对话标题" value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} />
            <button type="submit" disabled={!draftTitle.trim() || busy}>保存</button>
          </form>
        ) : (
          <>
            <button
              className={`sidebar-item ${conversation.conversation_id === activeConversationId ? 'is-current' : ''}`}
              type="button"
              title={title}
              onClick={() => onOpenConversation(conversation)}
            >
              {conversation.local_status === 'processing' ? (
                <LoaderCircle className="pending-spinner" size={16} aria-hidden="true" />
              ) : (
                <MessageSquare size={16} />
              )}
              <span>{title}</span>
              {conversation.local_status === 'processing' ? (
                <small className="pending-label">正在分析</small>
              ) : null}
              {conversation.local_status === 'failed' ? (
                <small className="failed-label">失败</small>
              ) : null}
            </button>
            <FloatingActionMenu
              label={`管理对话：${title}`}
              open={actionConversationId === conversation.conversation_id}
              onOpenChange={(open) => {
                setActionReportId(null)
                setActionConversationId(open ? conversation.conversation_id : null)
              }}
            >
              {conversation.local_status !== 'processing' ? <button type="button" role="menuitem" onClick={() => { setDraftTitle(title); setEditingConversationId(conversation.conversation_id); setActionConversationId(null) }}><Pencil size={15} />重命名</button> : null}
              {archived ? (
                <button type="button" role="menuitem" disabled={busy} onClick={() => void manage(conversation, () => onRestore(conversation))}><RotateCcw size={15} />恢复</button>
              ) : conversation.local_status !== 'processing' ? (
                <button type="button" role="menuitem" disabled={busy} onClick={() => void manage(conversation, () => onArchive(conversation))}><Archive size={15} />归档</button>
              ) : null}
              <button className="danger-action" type="button" role="menuitem" disabled={busy || conversation.local_status === 'processing'} onClick={() => {
                if (window.confirm(`删除“${title}”及其关联报表？此操作不可撤销。`)) void manage(conversation, () => onDelete(conversation))
              }}><Trash2 size={15} />删除</button>
            </FloatingActionMenu>
          </>
        )}
      </div>
    )
  })

  return (
    <>
    <aside className={`sidebar ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <div className="sidebar-brand-row">
        <div className="brand-mark" title="PowerBIAgent"><BarChart3 size={20} strokeWidth={1.8} /><strong>PowerBIAgent</strong></div>
        <button className="plain-icon-button" type="button" onClick={onToggle} aria-label={collapsed ? '展开侧栏' : '折叠侧栏'}>
          {collapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}
        </button>
      </div>

      <nav className="sidebar-primary" aria-label="主要导航">
        <button type="button" onClick={onNewChat} title="新聊天"><Plus size={20} /><span>新聊天</span></button>
        <button type="button" onClick={() => { if (collapsed) onToggle(); setSearchOpen(true) }} title="搜索聊天"><Search size={19} /><span>搜索聊天</span></button>
      </nav>

      {!collapsed && searchOpen ? (
        <section className="sidebar-search" aria-label="搜索聊天">
          <div className="sidebar-search-heading"><strong>搜索聊天</strong><button type="button" aria-label="关闭搜索" onClick={() => setSearchOpen(false)}><X size={16} /></button></div>
          <form onSubmit={(event) => { event.preventDefault(); void runSearch() }}>
            <input value={query} maxLength={200} autoFocus placeholder="搜索标题、问题或回答" aria-label="搜索标题、问题或回答" onChange={(event) => setQuery(event.target.value)} />
            <button type="submit" aria-label="执行搜索" disabled={!query.trim() || searching}><Search size={16} /></button>
          </form>
          {searching ? <p className="sidebar-state">正在搜索…</p> : null}
          {searchError ? <p className="sidebar-state sidebar-state-error">{searchError}</p> : null}
          {searchResults?.length === 0 && !searchError ? <p className="sidebar-state">没有找到相关对话</p> : null}
          {searchResults ? conversationRows(searchResults) : null}
        </section>
      ) : null}

      <div className="sidebar-scroll">
        <section className="sidebar-section project-section"><span className="sidebar-label">项目</span><div className="project-card" title="Power BI 销售分析"><Folder size={18} /><span>Power BI 销售分析</span></div></section>
        <section className="sidebar-section collapsible-section">
          <button className="sidebar-section-toggle" type="button" aria-expanded={reportsOpen} onClick={() => setReportsOpen((open) => !open)}><span>最近报表</span><ChevronDown className={reportsOpen ? 'is-open' : ''} size={15} /></button>
          {reportsOpen && reports.length === 0 ? <p className="sidebar-state">暂无最近报表</p> : reportsOpen ? reports.map((report) => isUsableReport(report) ? (
            <div className="sidebar-item-row" data-report-actions key={report.report_id}>
              <a className="sidebar-item" href={report.view_reference} target="_blank" rel="noreferrer" title={`查看${report.display_title || '销售分析报告'}`}><FileText size={17} /><span>{report.display_title || '销售分析报告'}</span></a>
              <FloatingActionMenu label={`管理报表：${report.display_title || '销售分析报告'}`} open={actionReportId === report.report_id} onOpenChange={(open) => { setActionConversationId(null); setActionReportId(open ? report.report_id : null) }}>
                  <button type="button" role="menuitem" disabled={managingReportId === report.report_id} onClick={() => {
                    const title = window.prompt('输入新的报表标题', report.display_title || '销售分析报告')?.trim()
                    if (title) void manageReport(report, () => onRenameReport(report, title))
                  }}><Pencil size={15} />重命名</button>
                  <button type="button" role="menuitem" disabled={managingReportId === report.report_id} onClick={() => {
                    void manageReport(report, () => onArchiveReport(report))
                  }}><Archive size={15} />归档</button>
                  <button className="danger-action" type="button" role="menuitem" disabled={managingReportId === report.report_id} onClick={() => {
                    if (window.confirm(`删除“${report.display_title || '销售分析报告'}”？此操作不可撤销，但不会删除所属对话。`)) void manageReport(report, () => onDeleteReport(report))
                  }}><Trash2 size={15} />删除报表</button>
              </FloatingActionMenu>
            </div>
          ) : null) : null}
        </section>
        <section className="sidebar-section collapsible-section recent-section">
          <button className="sidebar-section-toggle" type="button" aria-expanded={recentOpen} onClick={() => setRecentOpen((open) => !open)}><span>最近对话</span><ChevronDown className={recentOpen ? 'is-open' : ''} size={15} /></button>
          {recentOpen && error ? <p className="sidebar-state">{error}</p> : null}
          {recentOpen && !error && conversations.length === 0 ? <p className="sidebar-state">暂无最近对话</p> : null}
          {recentOpen ? <div className="recent-conversation-list">{conversationRows(conversations)}</div> : null}
          {actionError ? <p className="sidebar-state sidebar-state-error" role="alert">{actionError}</p> : null}
        </section>
      </div>
      <div className="account-actions" data-account-actions>
        {userMenuOpen && !collapsed ? <div className="account-menu" role="menu" aria-label="用户菜单">
          <button type="button" role="menuitem" onClick={() => { setResourceManagerOpen(true); setUserMenuOpen(false) }}><Settings size={16} />设置</button>
        </div> : null}
        <button className="account-card" type="button" title="PowerBIAgent 用户" aria-label="PowerBIAgent 用户" aria-haspopup="menu" aria-expanded={userMenuOpen} onClick={() => { if (collapsed) onToggle(); setUserMenuOpen((open) => !open) }}><span className="account-avatar"><UserRound size={16} /></span><span className="account-copy"><strong>PowerBIAgent</strong><small>内部用户</small></span></button>
      </div>
    </aside>
    {resourceManagerOpen ? <ResourceManager runtimeMode={runtimeMode} onClose={() => setResourceManagerOpen(false)} onRenameConversation={onRename} onBulkDeleteConversations={onBulkDeleteConversations} onBulkArchiveConversations={onBulkArchiveConversations} onBulkRestoreConversations={onBulkRestoreConversations} onBulkDeleteReports={onBulkDeleteReports} onBulkArchiveReports={onBulkArchiveReports} onBulkRestoreReports={onBulkRestoreReports} onRenameReport={onRenameReport} /> : null}
    </>
  )
}
