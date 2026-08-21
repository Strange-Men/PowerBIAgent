import {
  BarChart3,
  FileText,
  Folder,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Search,
  UserRound,
  X,
} from 'lucide-react'
import { useState } from 'react'
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
}

function displayTitle(conversation: ConversationSummary): string {
  return conversation.latest_analysis_goal?.trim() || '未命名对话'
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
}: SidebarProps) {
  const [searchOpen, setSearchOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<ConversationSummary[] | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)

  const runSearch = async () => {
    const normalized = query.trim()
    if (!normalized || searching) return
    setSearching(true)
    setSearchError(null)
    try {
      setSearchResults(await onSearch(normalized))
    } catch (searchFailure) {
      setSearchResults([])
      setSearchError(
        searchFailure instanceof Error
          ? searchFailure.message
          : '搜索暂时不可用，请稍后重试。',
      )
    } finally {
      setSearching(false)
    }
  }

  const openSearch = () => {
    if (collapsed) onToggle()
    setSearchOpen(true)
  }

  return (
    <aside className={`sidebar ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <div className="sidebar-brand-row">
        <div className="brand-mark" title="PowerBIAgent">
          <BarChart3 size={20} strokeWidth={1.8} />
          <strong>PowerBIAgent</strong>
        </div>
        <button className="plain-icon-button" type="button" onClick={onToggle} aria-label="折叠或展开侧栏">
          {collapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}
        </button>
      </div>

      <nav className="sidebar-primary" aria-label="主要导航">
        <button type="button" onClick={onNewChat} title="新聊天">
          <Plus size={20} />
          <span>新聊天</span>
        </button>
        <button type="button" onClick={openSearch} title="搜索聊天">
          <Search size={19} />
          <span>搜索聊天</span>
        </button>
      </nav>

      {!collapsed && searchOpen ? (
        <section className="sidebar-search" aria-label="搜索聊天">
          <div className="sidebar-search-heading">
            <strong>搜索聊天</strong>
            <button type="button" aria-label="关闭搜索" onClick={() => setSearchOpen(false)}>
              <X size={16} />
            </button>
          </div>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void runSearch()
            }}
          >
            <input
              value={query}
              maxLength={200}
              autoFocus
              placeholder="搜索分析主题"
              aria-label="搜索分析主题"
              onChange={(event) => setQuery(event.target.value)}
            />
            <button type="submit" disabled={!query.trim() || searching}>
              <Search size={16} />
            </button>
          </form>
          {searching ? <p className="sidebar-state">正在搜索…</p> : null}
          {searchError ? <p className="sidebar-state sidebar-state-error">{searchError}</p> : null}
          {searchResults?.length === 0 && !searchError ? (
            <p className="sidebar-state">没有找到相关对话</p>
          ) : null}
          {searchResults?.map((conversation) => (
            <button
              className="sidebar-result"
              type="button"
              key={conversation.conversation_id}
              onClick={() => {
                onOpenConversation(conversation)
                setSearchOpen(false)
              }}
            >
              <MessageSquare size={15} />
              <span>{displayTitle(conversation)}</span>
            </button>
          ))}
        </section>
      ) : null}

      <div className="sidebar-scroll">
        <section className="sidebar-section project-section">
          <span className="sidebar-label">项目</span>
          <div className="project-card" title="Power BI 销售分析">
            <Folder size={18} />
            <span>Power BI 销售分析</span>
          </div>
        </section>

        <section className="sidebar-section">
          <span className="sidebar-label">最近报表</span>
          {reports.length === 0 ? (
            <p className="sidebar-state">暂无最近报表</p>
          ) : (
            reports.map((report) =>
              isUsableReport(report) ? (
                <a
                  className="sidebar-item"
                  href={report.view_reference}
                  target="_blank"
                  rel="noreferrer"
                  key={report.report_id}
                  title="查看销售分析报告"
                >
                  <FileText size={17} />
                  <span>销售分析报告</span>
                </a>
              ) : null,
            )
          )}
        </section>

        <section className="sidebar-section">
          <span className="sidebar-label">最近</span>
          {error ? <p className="sidebar-state">{error}</p> : null}
          {!error && conversations.length === 0 ? (
            <p className="sidebar-state">暂无最近对话</p>
          ) : null}
          {conversations.map((conversation) => (
            <button
              className={`sidebar-item ${
                conversation.conversation_id === activeConversationId ? 'is-current' : ''
              }`}
              type="button"
              key={conversation.conversation_id}
              title={displayTitle(conversation)}
              onClick={() => onOpenConversation(conversation)}
            >
              <MessageSquare size={16} />
              <span>{displayTitle(conversation)}</span>
            </button>
          ))}
        </section>
      </div>

      <div className="account-card" title="PowerBIAgent 用户">
        <span className="account-avatar">
          <UserRound size={16} />
        </span>
        <span className="account-copy">
          <strong>PowerBIAgent</strong>
          <small>内部用户</small>
        </span>
      </div>
    </aside>
  )
}
