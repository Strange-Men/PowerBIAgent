import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  listArchivedConversations,
  listManagedReports,
  listRecentConversations,
} from '../api/client'
import type {
  BatchOperationResult,
  ConversationReportItem,
  ConversationSummary,
} from '../types'
import { ResourceManager } from './ResourceManager'

vi.mock('../api/client', () => ({
  listArchivedConversations: vi.fn(),
  listManagedReports: vi.fn(),
  listRecentConversations: vi.fn(),
}))

const conversations = Array.from({ length: 35 }, (_, index) => ({
  runtime_mode: 'real' as const,
  conversation_id: `conversation-${String(index + 1).padStart(2, '0')}`,
  created_at: '2026-08-24T10:00:00',
  updated_at: `2026-08-24T10:${String(index).padStart(2, '0')}:00`,
  archived_at: null,
  title: `历史对话 ${index + 1}`,
  latest_request_id: `request-${index + 1}`,
  latest_terminal_state: 'completed',
  latest_response_type: 'answer',
  latest_analysis_goal: null,
})) satisfies ConversationSummary[]

const archivedConversation: ConversationSummary = {
  ...conversations[0],
  conversation_id: 'archived-conversation-1',
  archived_at: '2026-08-24T11:00:00',
  title: '已归档销售分析',
}

const reports = Array.from({ length: 30 }, (_, index) => ({
  report_id: `report-${String(index + 1).padStart(2, '0')}`,
  template_key: 'sales_report',
  contract_version: '1.0',
  view_reference: `/api/reports/report-${index + 1}`,
  download_reference: `/api/reports/report-${index + 1}/download`,
  content_type: 'text/html; charset=utf-8',
  content_hash: 'a'.repeat(64),
  display_title: `历史报表 ${index + 1}`,
  availability_status: 'available' as const,
  source_mode: 'real' as const,
  conversation_id: conversations[index % conversations.length].conversation_id,
  request_id: `request-${index + 1}`,
  semantic_model_key: 'model',
  generated_at: '2026-08-24T10:00:00',
  stored_at: '2026-08-24T10:00:00',
  archived_at: null,
})) satisfies ConversationReportItem[]

const archivedReport: ConversationReportItem = {
  ...reports[0],
  report_id: 'archived-report-1',
  display_title: '已归档报表',
  archived_at: '2026-08-24T11:00:00',
}

function page<T>(items: T[], cursor?: string) {
  const offset = cursor ? 20 : 0
  return {
    items: items.slice(offset, offset + 20),
    next_cursor: offset + 20 < items.length ? 'page-2' : null,
    total_count: items.length,
  }
}

function batchResult<T>(items: T[], id: (item: T) => string) {
  return Promise.resolve({
    succeededIds: items.map(id),
    failed: [],
  })
}

function setup(overrides?: {
  onBulkDeleteConversations?: (
    items: ConversationSummary[],
  ) => Promise<BatchOperationResult>
}) {
  const onBulkDeleteConversations =
    overrides?.onBulkDeleteConversations ??
    vi.fn((items: ConversationSummary[]) =>
      batchResult(items, (item) => item.conversation_id),
    )
  const props = {
    runtimeMode: 'real' as const,
    onClose: vi.fn(),
    onRenameConversation: vi.fn().mockResolvedValue(undefined),
    onBulkDeleteConversations,
    onBulkArchiveConversations: vi.fn((items: ConversationSummary[]) =>
      batchResult(items, (item) => item.conversation_id),
    ),
    onBulkRestoreConversations: vi.fn((items: ConversationSummary[]) =>
      batchResult(items, (item) => item.conversation_id),
    ),
    onBulkDeleteReports: vi.fn((items: ConversationReportItem[]) =>
      batchResult(items, (item) => item.report_id),
    ),
    onBulkArchiveReports: vi.fn((items: ConversationReportItem[]) =>
      batchResult(items, (item) => item.report_id),
    ),
    onBulkRestoreReports: vi.fn((items: ConversationReportItem[]) =>
      batchResult(items, (item) => item.report_id),
    ),
    onRenameReport: vi.fn().mockResolvedValue(undefined),
  }
  render(<ResourceManager {...props} />)
  return props
}

beforeEach(() => {
  vi.mocked(listRecentConversations).mockImplementation(
    (_mode, _limit, cursor) =>
      Promise.resolve({ runtime_mode: 'real', ...page(conversations, cursor) }),
  )
  vi.mocked(listArchivedConversations).mockImplementation(
    (_mode, _limit, cursor) =>
      Promise.resolve({
        runtime_mode: 'real',
        ...page([archivedConversation], cursor),
      }),
  )
  vi.mocked(listManagedReports).mockImplementation(
    (_mode, status, _limit, cursor) =>
      Promise.resolve({
        source_mode: 'real',
        status,
        ...page(status === 'active' ? reports : [archivedReport], cursor),
      }),
  )
})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('ResourceManager full-history pagination', () => {
  it('loads its own first page and can reach all 35 conversations', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /对话管理/ }))

    expect(await screen.findByText('共 35 项 · 已加载 20 项')).toBeInTheDocument()
    expect(screen.queryByText('历史对话 35')).not.toBeInTheDocument()
    expect(listRecentConversations).toHaveBeenCalledWith('real', 20, undefined)

    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    expect(await screen.findByText('历史对话 35')).toBeInTheDocument()
    expect(screen.getByText('共 35 项 · 已加载 35 项')).toBeInTheDocument()
    expect(screen.getByText('已加载全部 35 项')).toBeInTheDocument()
  })

  it('makes select-loaded semantics explicit across pagination', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /对话管理/ }))
    await screen.findByText('共 35 项 · 已加载 20 项')

    fireEvent.click(screen.getByRole('button', { name: '全选当前已加载' }))
    expect(screen.getByText('已选择 20 / 共 35 项')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await screen.findByText('历史对话 35')
    expect(screen.getByText('已选择 20 / 共 35 项')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '全选当前已加载' }))
    expect(screen.getByText('已选择 35 / 共 35 项')).toBeInTheDocument()
  })

  it('loads all 30 reports independently of recent conversations', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /报表管理/ }))

    expect(await screen.findByText('共 30 项 · 已加载 20 项')).toBeInTheDocument()
    expect(listManagedReports).toHaveBeenCalledWith(
      'real',
      'active',
      20,
      undefined,
    )
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    expect(await screen.findByText('历史报表 30')).toBeInTheDocument()
    expect(screen.getByText('已加载全部 30 项')).toBeInTheDocument()
  })
})

describe('ResourceManager lifecycle operations', () => {
  it('keeps the resource toolbar outside the independently scrollable list', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /对话管理/ }))
    await screen.findByText('共 35 项 · 已加载 20 项')

    const list = screen.getByRole('region', { name: '对话管理资源列表' })
    const toolbar = screen.getByRole('toolbar', { name: '对话管理操作栏' })
    const dialog = screen.getByRole('dialog', { name: '设置' })
    expect(dialog.querySelector(':scope > .settings-header')).toBeInTheDocument()
    expect(dialog.querySelector(':scope > .settings-layout')).toBeInTheDocument()
    expect(list.nextElementSibling).toBe(toolbar)
    expect(toolbar).toContainElement(screen.getByRole('button', { name: /批量删除/ }))
  })

  it('passes every loaded selection to one confirmed operation', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    const actions = setup()
    fireEvent.click(screen.getByRole('button', { name: /对话管理/ }))
    await screen.findByText('共 35 项 · 已加载 20 项')
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await screen.findByText('历史对话 35')
    fireEvent.click(screen.getByRole('button', { name: '全选当前已加载' }))
    fireEvent.click(screen.getByRole('button', { name: /批量删除/ }))

    await waitFor(() =>
      expect(actions.onBulkDeleteConversations).toHaveBeenCalledWith(
        conversations,
      ),
    )
    expect(window.confirm).toHaveBeenCalledWith(
      '删除选中的 35 个对话及其关联报表？此操作不可撤销。',
    )
  })

  it('keeps failed resources selected and reports the exact failure', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    const failing = vi.fn().mockResolvedValue({
      succeededIds: [],
      failed: [{ id: conversations[0].conversation_id, reason: '仍在运行' }],
    })
    setup({ onBulkDeleteConversations: failing })
    fireEvent.click(screen.getByRole('button', { name: /对话管理/ }))
    await screen.findByText('共 35 项 · 已加载 20 项')
    fireEvent.click(
      screen.getByRole('checkbox', { name: /选择对话：历史对话 1$/ }),
    )
    fireEvent.click(screen.getByRole('button', { name: /批量删除/ }))

    expect(
      await screen.findByText(/1 项失败：conversation-01（仍在运行）/),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('checkbox', { name: /选择对话：历史对话 1$/ }),
    ).toBeChecked()
  })

  it('shows archived conversations and reports in separate pageable sections', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /已归档/ }))

    expect(await screen.findByText('已归档销售分析')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '已归档报表' }),
    ).toBeInTheDocument()
    expect(screen.getAllByText('共 1 项 · 已加载 1 项')).toHaveLength(2)
  })
})
