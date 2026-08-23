import {
  Archive,
  BarChart3,
  FileText,
  Folder,
  MessageSquare,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Search,
  Trash2,
  UserRound,
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { isUsableReport } from '../api/adapters'
import type { ConversationReportItem, ConversationSummary } from '../types'

interface SidebarProps {
  collapsed: boolean
  activeConversationId: string | null
  conversations: ConversationSummary[]
  reports: ConversationReportItem[]
  error: string | null
  onToggle: () => void
  onNewChat: () => void
  onOpenConversation: (conversation: ConversationSummary) => void
  onSearch: (query: string) => Promise<ConversationSummary[]>
  onRename: (conversation: ConversationSummary, title: string) => Promise<void>
  onArchive: (conversation: ConversationSummary) => Promise<void>
  onDelete: (conversation: ConversationSummary) => Promise<void>
}

function displayTitle(conversation: ConversationSummary): string {
  return conversation.title?.trim() || conversation.latest_analysis_goal?.replace(/^用户提问:\s*/, '').trim() || '未命名对话'
}

export function Sidebar({
  collapsed,
  activeConversationId,
  conversations,
  reports,
  error,
  onToggle,
  onNewChat,
  onOpenConversation,
  onSearch,
  onRename,
  onArchive,
  onDelete,
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

  useEffect(() => {
    const closeMenus = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setActionConversationId(null)
      setEditingConversationId(null)
      setSearchOpen(false)
    }
    const closeActionMenu = (event: MouseEvent) => {
      const target = event.target
      if (target instanceof Element && !target.closest('[data-conversation-actions]')) {
        setActionConversationId(null)
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

  const conversationRows = (items: ConversationSummary[]) => items.map((conversation) => {
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
              <MessageSquare size={16} /><span>{title}</span>
            </button>
            <button
              className="conversation-actions-trigger"
              type="button"
              aria-label={`管理对话：${title}`}
              aria-haspopup="menu"
              aria-expanded={actionConversationId === conversation.conversation_id}
              onClick={() => setActionConversationId((current) => current === conversation.conversation_id ? null : conversation.conversation_id)}
            >
              <MoreHorizontal size={17} />
            </button>
          </>
        )}
        {actionConversationId === conversation.conversation_id && !isEditing ? (
          <div className="conversation-actions-menu" role="menu" aria-label={`对话操作：${title}`}>
            <button type="button" role="menuitem" onClick={() => { setDraftTitle(title); setEditingConversationId(conversation.conversation_id); setActionConversationId(null) }}><Pencil size={15} />重命名</button>
            <button type="button" role="menuitem" disabled={busy} onClick={() => void manage(conversation, () => onArchive(conversation))}><Archive size={15} />归档</button>
            <button className="danger-action" type="button" role="menuitem" disabled={busy} onClick={() => {
              if (window.confirm(`删除“${title}”及其关联报表？此操作不可撤销。`)) void manage(conversation, () => onDelete(conversation))
            }}><Trash2 size={15} />删除</button>
          </div>
        ) : null}
      </div>
    )
  })

  return (
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
        <section className="sidebar-section">
          <span className="sidebar-label">最近报表</span>
          {reports.length === 0 ? <p className="sidebar-state">暂无最近报表</p> : reports.map((report) => isUsableReport(report) ? (
            <a className="sidebar-item" href={report.view_reference} target="_blank" rel="noreferrer" key={report.report_id} title="查看销售分析报告"><FileText size={17} /><span>销售分析报告</span></a>
          ) : null)}
          {reports.length > 0 ? <p className="sidebar-state">报表随所属对话归档或删除。</p> : null}
        </section>
        <section className="sidebar-section">
          <span className="sidebar-label">最近</span>
          {error ? <p className="sidebar-state">{error}</p> : null}
          {!error && conversations.length === 0 ? <p className="sidebar-state">暂无最近对话</p> : null}
          {conversationRows(conversations)}
          {actionError ? <p className="sidebar-state sidebar-state-error" role="alert">{actionError}</p> : null}
        </section>
      </div>
      <div className="account-card" title="PowerBIAgent 用户"><span className="account-avatar"><UserRound size={16} /></span><span className="account-copy"><strong>PowerBIAgent</strong><small>内部用户</small></span></div>
    </aside>
  )
}
