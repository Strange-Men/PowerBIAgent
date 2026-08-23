import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ConversationSummary } from '../types'
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

afterEach(() => vi.unstubAllGlobals())

function renderSidebar() {
  const onRename = vi.fn().mockResolvedValue(undefined)
  const onArchive = vi.fn().mockResolvedValue(undefined)
  const onDelete = vi.fn().mockResolvedValue(undefined)
  render(
    <Sidebar
      collapsed={false}
      activeConversationId={null}
      conversations={[conversation]}
      reports={[]}
      error={null}
      onToggle={vi.fn()}
      onNewChat={vi.fn()}
      onOpenConversation={vi.fn()}
      onSearch={vi.fn().mockResolvedValue([])}
      onRename={onRename}
      onArchive={onArchive}
      onDelete={onDelete}
    />,
  )
  return { onRename, onArchive, onDelete }
}

describe('Sidebar conversation management', () => {
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
})
