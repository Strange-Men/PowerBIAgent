import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type {
  BatchOperationResult,
  ConversationReportItem,
  ConversationSummary,
} from '../types'
import { ResourceManager } from './ResourceManager'

const recent: ConversationSummary = {
  runtime_mode: 'real',
  conversation_id: 'recent-1',
  created_at: '2026-08-24T10:00:00',
  updated_at: '2026-08-24T10:01:00',
  archived_at: null,
  title: '最近销售分析',
  latest_request_id: 'request-1',
  latest_terminal_state: 'completed',
  latest_response_type: 'answer',
  latest_analysis_goal: null,
}

const archived: ConversationSummary = {
  ...recent,
  conversation_id: 'archived-1',
  archived_at: '2026-08-24T11:00:00',
  title: '已归档销售分析',
}

const report: ConversationReportItem = {
  report_id: 'rpt-1',
  template_key: 'sales_report',
  contract_version: '1.0',
  view_reference: '/api/reports/rpt-1',
  download_reference: '/api/reports/rpt-1/download',
  content_type: 'text/html; charset=utf-8',
  content_hash: 'a'.repeat(64),
  display_title: '八月销售报告',
  availability_status: 'available',
  source_mode: 'real',
  conversation_id: recent.conversation_id,
  request_id: 'request-1',
  semantic_model_key: 'model',
  generated_at: '2026-08-24T10:00:00',
  stored_at: '2026-08-24T10:00:00',
}

afterEach(() => vi.unstubAllGlobals())

function setup(overrides?: {
  onBulkDeleteConversations?: (
    items: ConversationSummary[],
  ) => Promise<BatchOperationResult>
}) {
  const onBulkDeleteConversations =
    overrides?.onBulkDeleteConversations ||
    vi.fn().mockImplementation(async (items: ConversationSummary[]) => ({
      succeededIds: items.map((item) => item.conversation_id),
      failed: [],
    }))
  const onBulkRestoreConversations = vi
    .fn()
    .mockImplementation(async (items: ConversationSummary[]) => ({
      succeededIds: items.map((item) => item.conversation_id),
      failed: [],
    }))
  const onBulkDeleteReports = vi
    .fn()
    .mockImplementation(async (items: ConversationReportItem[]) => ({
      succeededIds: items.map((item) => item.report_id),
      failed: [],
    }))
  const onRenameReport = vi.fn().mockResolvedValue(undefined)
  render(
    <ResourceManager
      conversations={[recent]}
      archivedConversations={[archived]}
      reports={[report]}
      onClose={vi.fn()}
      onBulkDeleteConversations={onBulkDeleteConversations}
      onBulkRestoreConversations={onBulkRestoreConversations}
      onBulkDeleteReports={onBulkDeleteReports}
      onRenameReport={onRenameReport}
    />,
  )
  return {
    onBulkDeleteConversations,
    onBulkRestoreConversations,
    onBulkDeleteReports,
    onRenameReport,
  }
}

describe('ResourceManager', () => {
  it('coordinates recent delete plus archived restore/delete through explicit APIs', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    const actions = setup()

    fireEvent.click(screen.getByRole('checkbox', { name: /最近销售分析/ }))
    fireEvent.click(screen.getAllByRole('button', { name: '批量删除' })[0])
    await waitFor(() =>
      expect(actions.onBulkDeleteConversations).toHaveBeenCalledWith([recent]),
    )

    fireEvent.click(screen.getByRole('checkbox', { name: /已归档销售分析/ }))
    fireEvent.click(screen.getByRole('button', { name: '批量恢复' }))
    await waitFor(() =>
      expect(actions.onBulkRestoreConversations).toHaveBeenCalledWith([archived]),
    )

    fireEvent.click(screen.getByRole('checkbox', { name: /已归档销售分析/ }))
    fireEvent.click(screen.getAllByRole('button', { name: '批量删除' })[1])
    await waitFor(() =>
      expect(actions.onBulkDeleteConversations).toHaveBeenLastCalledWith([
        archived,
      ]),
    )
  })

  it('renames one report and batch deletes selected reports', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    const actions = setup()

    fireEvent.click(screen.getByRole('button', { name: '重命名' }))
    fireEvent.change(screen.getByLabelText('新报表标题'), {
      target: { value: '区域销售报告' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() =>
      expect(actions.onRenameReport).toHaveBeenCalledWith(report, '区域销售报告'),
    )

    fireEvent.click(screen.getByRole('checkbox', { name: /选择报表/ }))
    fireEvent.click(screen.getAllByRole('button', { name: '批量删除' })[2])
    await waitFor(() =>
      expect(actions.onBulkDeleteReports).toHaveBeenCalledWith([report]),
    )
  })

  it('reports partial failure without pretending the whole batch succeeded', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    const failing = vi.fn().mockResolvedValue({
      succeededIds: [],
      failed: [{ id: recent.conversation_id, reason: '仍在运行' }],
    })
    setup({ onBulkDeleteConversations: failing })

    fireEvent.click(screen.getByRole('checkbox', { name: /最近销售分析/ }))
    fireEvent.click(screen.getAllByRole('button', { name: '批量删除' })[0])
    expect(await screen.findByText(/1 项失败：仍在运行/)).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /最近销售分析/ })).toBeChecked()
  })
})
