import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ConversationReportItem, ConversationSummary } from '../types'
import { Sidebar } from './Sidebar'

const conversation: ConversationSummary = {
  runtime_mode: 'real',
  conversation_id: 'm53-test-conversation',
  created_at: '2026-08-23T10:00:00',
  updated_at: '2026-08-23T10:01:00',
  archived_at: null,
  title: '八月销售复盘',
  latest_request_id: 'request-1',
  latest_terminal_state: 'completed',
  latest_response_type: 'answer',
  latest_analysis_goal: '用户提问: 查看八月销售',
}

const report: ConversationReportItem = {
  report_id: 'report-1',
  template_key: 'sales_report',
  contract_version: '1.0',
  view_reference: '/api/reports/report-1',
  download_reference: '/api/reports/report-1/download',
  content_type: 'text/html; charset=utf-8',
  content_hash: 'a'.repeat(64),
  source_mode: 'real',
  conversation_id: conversation.conversation_id,
  request_id: 'request-1',
  semantic_model_key: 'model',
  generated_at: '2026-08-23T10:00:00',
  stored_at: '2026-08-23T10:00:00',
}

afterEach(() => vi.unstubAllGlobals())

function renderSidebar(currentConversation: ConversationSummary = conversation) {
  const onRename = vi.fn().mockResolvedValue(undefined)
  const onArchive = vi.fn().mockResolvedValue(undefined)
  const onDelete = vi.fn().mockResolvedValue(undefined)
  const onRestore = vi.fn().mockResolvedValue(undefined)
  const onDeleteReport = vi.fn().mockResolvedValue(undefined)
  const onRenameReport = vi.fn().mockResolvedValue(undefined)
  const batchResult = { succeededIds: [], failed: [] }
  render(
    <Sidebar
      collapsed={false}
      activeConversationId={null}
      conversations={[currentConversation]}
      archivedConversations={[]}
      reports={[report]}
      error={null}
      onToggle={vi.fn()}
      onNewChat={vi.fn()}
      onOpenConversation={vi.fn()}
      onSearch={vi.fn().mockResolvedValue([])}
      onRename={onRename}
      onArchive={onArchive}
      onRestore={onRestore}
      onDelete={onDelete}
      onDeleteReport={onDeleteReport}
      onRenameReport={onRenameReport}
      onBulkDeleteConversations={vi.fn().mockResolvedValue(batchResult)}
      onBulkRestoreConversations={vi.fn().mockResolvedValue(batchResult)}
      onBulkDeleteReports={vi.fn().mockResolvedValue(batchResult)}
    />,
  )
  return { onRename, onArchive, onDelete, onRestore, onDeleteReport }
}

describe('Sidebar conversation management', () => {
  it('keeps presentation actions available after a provisional conversation becomes ready', () => {
    renderSidebar({ ...conversation, local_status: 'ready' })
    fireEvent.click(screen.getByRole('button', { name: /管理对话：八月销售复盘/ }))
    expect(screen.getByRole('menuitem', { name: /重命名/ })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /归档/ })).toBeInTheDocument()
  })

  it('renames a conversation through the inline presentation title editor', async () => {
    const { onRename } = renderSidebar()
    fireEvent.click(screen.getByRole('button', { name: /管理对话：八月销售复盘/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /重命名/ }))
    const input = screen.getByLabelText('新对话标题')
    fireEvent.change(input, { target: { value: '区域销售复盘' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(onRename).toHaveBeenCalledWith(conversation, '区域销售复盘'))
  })

  it('archives from the menu and closes menus with Escape', async () => {
    const { onArchive } = renderSidebar()
    const trigger = screen.getByRole('button', { name: /管理对话/ })
    fireEvent.click(trigger)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    fireEvent.click(trigger)
    fireEvent.click(screen.getByRole('menuitem', { name: /归档/ }))
    await waitFor(() => expect(onArchive).toHaveBeenCalledWith(conversation))
  })

  it('requires confirmation before deleting the owning conversation', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    const { onDelete } = renderSidebar()
    fireEvent.click(screen.getByRole('button', { name: /管理对话/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /删除/ }))
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(conversation))
  })

  it('requires the explicit irreversible confirmation before deleting only a report', async () => {
    const confirm = vi.fn().mockReturnValue(true)
    vi.stubGlobal('confirm', confirm)
    const { onDeleteReport } = renderSidebar()
    fireEvent.click(screen.getByRole('button', { name: '管理报表：销售分析报告' }))
    fireEvent.click(screen.getByRole('menuitem', { name: /删除报表/ }))
    expect(confirm).toHaveBeenCalledWith(
      '删除“销售分析报告”？此操作不可撤销，但不会删除所属对话。',
    )
    await waitFor(() => expect(onDeleteReport).toHaveBeenCalledWith(report))
  })

  it('shows archived conversations and restores them from their menu', async () => {
    const onRestore = vi.fn().mockResolvedValue(undefined)
    render(
      <Sidebar
        collapsed={false}
        activeConversationId={null}
        conversations={[]}
        archivedConversations={[{ ...conversation, archived_at: '2026-08-24T10:00:00' }]}
        reports={[]}
        error={null}
        onToggle={vi.fn()}
        onNewChat={vi.fn()}
        onOpenConversation={vi.fn()}
        onSearch={vi.fn().mockResolvedValue([])}
        onRename={vi.fn().mockResolvedValue(undefined)}
        onArchive={vi.fn().mockResolvedValue(undefined)}
        onRestore={onRestore}
        onDelete={vi.fn().mockResolvedValue(undefined)}
        onDeleteReport={vi.fn().mockResolvedValue(undefined)}
        onRenameReport={vi.fn().mockResolvedValue(undefined)}
        onBulkDeleteConversations={vi.fn().mockResolvedValue({ succeededIds: [], failed: [] })}
        onBulkRestoreConversations={vi.fn().mockResolvedValue({ succeededIds: [conversation.conversation_id], failed: [] })}
        onBulkDeleteReports={vi.fn().mockResolvedValue({ succeededIds: [], failed: [] })}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'PowerBIAgent 用户' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '已归档' }))
    expect(screen.getByRole('heading', { name: '已归档' })).toBeInTheDocument()
    expect(screen.getByText('八月销售复盘')).toBeInTheDocument()
    expect(onRestore).not.toHaveBeenCalled()
  })

  it('shows pending status immediately and keeps recent/report sections collapsible', () => {
    renderSidebar()
    expect(screen.getByRole('button', { name: '最近对话' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    fireEvent.click(screen.getByRole('button', { name: '最近对话' }))
    expect(screen.queryByText('八月销售复盘')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '最近报表' }))
    expect(screen.queryByText('销售分析报告')).not.toBeInTheDocument()
  })
})
