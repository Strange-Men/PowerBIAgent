import { FileText, MessageSquare, RotateCcw, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import type {
  BatchOperationResult,
  ConversationReportItem,
  ConversationSummary,
} from '../types'

interface ResourceManagerProps {
  conversations: ConversationSummary[]
  archivedConversations: ConversationSummary[]
  reports: ConversationReportItem[]
  onClose: () => void
  onBulkDeleteConversations: (
    items: ConversationSummary[],
  ) => Promise<BatchOperationResult>
  onBulkRestoreConversations: (
    items: ConversationSummary[],
  ) => Promise<BatchOperationResult>
  onBulkDeleteReports: (
    items: ConversationReportItem[],
  ) => Promise<BatchOperationResult>
  onRenameReport: (
    report: ConversationReportItem,
    displayTitle: string,
  ) => Promise<void>
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

function failureReason(error: unknown): string {
  return error instanceof Error ? error.message : '操作未完成，请稍后重试。'
}

function selectionItems<T extends { conversation_id: string }>(
  items: T[],
  selected: Set<string>,
): T[] {
  return items.filter((item) => selected.has(item.conversation_id))
}

export function ResourceManager({
  conversations,
  archivedConversations,
  reports,
  onClose,
  onBulkDeleteConversations,
  onBulkRestoreConversations,
  onBulkDeleteReports,
  onRenameReport,
}: ResourceManagerProps) {
  const [recentSelected, setRecentSelected] = useState(new Set<string>())
  const [archivedSelected, setArchivedSelected] = useState(new Set<string>())
  const [reportSelected, setReportSelected] = useState(new Set<string>())
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [editingReportId, setEditingReportId] = useState<string | null>(null)
  const [reportDraft, setReportDraft] = useState('')

  const toggle = (
    setter: React.Dispatch<React.SetStateAction<Set<string>>>,
    id: string,
  ) => {
    setter((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const showOutcome = (result: BatchOperationResult) => {
    if (result.failed.length === 0) {
      setNotice(`已完成 ${result.succeededIds.length} 项操作。`)
      return
    }
    setNotice(
      `已完成 ${result.succeededIds.length} 项，${result.failed.length} 项失败：${result.failed
        .map((item) => item.reason)
        .join('；')}`,
    )
  }

  const run = async (operation: () => Promise<BatchOperationResult>) => {
    setBusy(true)
    setNotice(null)
    try {
      showOutcome(await operation())
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '操作未完成，请稍后重试。')
    } finally {
      setBusy(false)
    }
  }

  const selectAll = (
    setter: React.Dispatch<React.SetStateAction<Set<string>>>,
    ids: string[],
  ) => setter(new Set(ids.slice(0, 20)))

  return (
    <div className="resource-manager-backdrop" role="presentation">
      <section
        className="resource-manager"
        role="dialog"
        aria-modal="true"
        aria-labelledby="resource-manager-title"
      >
        <header>
          <div>
            <span className="resource-manager-eyebrow">设置</span>
            <h2 id="resource-manager-title">资源管理</h2>
            <p>单次最多处理 20 项；归档保留数据，删除不可撤销。</p>
          </div>
          <button type="button" aria-label="关闭设置" onClick={onClose}>
            <X size={19} />
          </button>
        </header>

        {notice ? <p className="resource-manager-notice" role="status">{notice}</p> : null}

        <div className="resource-manager-sections">
          <ResourceSection
            title="最近对话"
            empty="暂无最近对话"
            count={recentSelected.size}
            onSelectAll={() =>
              selectAll(
                setRecentSelected,
                conversations.map((item) => item.conversation_id),
              )
            }
            actions={
              <button
                className="danger-action"
                type="button"
                disabled={busy || recentSelected.size === 0}
                onClick={() => {
                  const selected = selectionItems(conversations, recentSelected)
                  if (
                    window.confirm(
                      `删除选中的 ${selected.length} 个对话及其关联报表？此操作不可撤销。`,
                    )
                  ) {
                    void run(async () => {
                      const result = await onBulkDeleteConversations(selected)
                      setRecentSelected(
                        (current) =>
                          new Set(
                            [...current].filter(
                              (id) => !result.succeededIds.includes(id),
                            ),
                          ),
                      )
                      return result
                    })
                  }
                }}
              >
                <Trash2 size={15} />批量删除
              </button>
            }
          >
            {conversations.map((item) => (
              <label className="resource-row" key={item.conversation_id}>
                <input
                  type="checkbox"
                  checked={recentSelected.has(item.conversation_id)}
                  onChange={() =>
                    toggle(setRecentSelected, item.conversation_id)
                  }
                />
                <MessageSquare size={16} />
                <span>{conversationTitle(item)}</span>
                {item.local_status === 'processing' ? <small>正在分析</small> : null}
                {item.local_status === 'failed' ? <small className="resource-error">失败</small> : null}
              </label>
            ))}
          </ResourceSection>

          <ResourceSection
            title="已归档"
            empty="暂无已归档对话"
            count={archivedSelected.size}
            onSelectAll={() =>
              selectAll(
                setArchivedSelected,
                archivedConversations.map((item) => item.conversation_id),
              )
            }
            actions={
              <>
                <button
                  type="button"
                  disabled={busy || archivedSelected.size === 0}
                  onClick={() => {
                    const selected = selectionItems(
                      archivedConversations,
                      archivedSelected,
                    )
                    void run(async () => {
                      const result = await onBulkRestoreConversations(selected)
                      setArchivedSelected(
                        (current) =>
                          new Set(
                            [...current].filter(
                              (id) => !result.succeededIds.includes(id),
                            ),
                          ),
                      )
                      return result
                    })
                  }}
                >
                  <RotateCcw size={15} />批量恢复
                </button>
                <button
                  className="danger-action"
                  type="button"
                  disabled={busy || archivedSelected.size === 0}
                  onClick={() => {
                    const selected = selectionItems(
                      archivedConversations,
                      archivedSelected,
                    )
                    if (
                      window.confirm(
                        `永久删除选中的 ${selected.length} 个已归档对话？`,
                      )
                    ) {
                      void run(async () => {
                        const result = await onBulkDeleteConversations(selected)
                        setArchivedSelected(
                          (current) =>
                            new Set(
                              [...current].filter(
                                (id) => !result.succeededIds.includes(id),
                              ),
                            ),
                        )
                        return result
                      })
                    }
                  }}
                >
                  <Trash2 size={15} />批量删除
                </button>
              </>
            }
          >
            {archivedConversations.map((item) => (
              <label className="resource-row" key={item.conversation_id}>
                <input
                  type="checkbox"
                  checked={archivedSelected.has(item.conversation_id)}
                  onChange={() =>
                    toggle(setArchivedSelected, item.conversation_id)
                  }
                />
                <MessageSquare size={16} />
                <span>{conversationTitle(item)}</span>
              </label>
            ))}
          </ResourceSection>

          <ResourceSection
            title="最近报表"
            empty="暂无最近报表"
            count={reportSelected.size}
            onSelectAll={() =>
              selectAll(
                setReportSelected,
                reports.map((item) => item.report_id),
              )
            }
            actions={
              <button
                className="danger-action"
                type="button"
                disabled={busy || reportSelected.size === 0}
                onClick={() => {
                  const selected = reports.filter((item) =>
                    reportSelected.has(item.report_id),
                  )
                  if (
                    window.confirm(
                      `删除选中的 ${selected.length} 个报表？所属对话会保留删除记录。`,
                    )
                  ) {
                    void run(async () => {
                      const result = await onBulkDeleteReports(selected)
                      setReportSelected(
                        (current) =>
                          new Set(
                            [...current].filter(
                              (id) => !result.succeededIds.includes(id),
                            ),
                          ),
                      )
                      return result
                    })
                  }
                }}
              >
                <Trash2 size={15} />批量删除
              </button>
            }
          >
            {reports.map((item) => (
              <div className="resource-row" key={item.report_id}>
                <input
                  aria-label={`选择报表：${reportTitle(item)}`}
                  type="checkbox"
                  checked={reportSelected.has(item.report_id)}
                  onChange={() => toggle(setReportSelected, item.report_id)}
                />
                <FileText size={16} />
                {editingReportId === item.report_id ? (
                  <form
                    className="resource-rename-form"
                    onSubmit={(event) => {
                      event.preventDefault()
                      const normalized = reportDraft.trim()
                      if (!normalized) return
                      setBusy(true)
                      setNotice(null)
                      void onRenameReport(item, normalized)
                        .then(() => {
                          setEditingReportId(null)
                          setNotice('报表标题已更新。')
                        })
                        .catch((error) => setNotice(failureReason(error)))
                        .finally(() => setBusy(false))
                    }}
                  >
                    <input
                      autoFocus
                      aria-label="新报表标题"
                      maxLength={120}
                      value={reportDraft}
                      onChange={(event) => setReportDraft(event.target.value)}
                    />
                    <button type="submit" disabled={busy || !reportDraft.trim()}>
                      保存
                    </button>
                  </form>
                ) : (
                  <>
                    <span>{reportTitle(item)}</span>
                    <button
                      className="resource-inline-action"
                      type="button"
                      onClick={() => {
                        setEditingReportId(item.report_id)
                        setReportDraft(reportTitle(item))
                      }}
                    >
                      重命名
                    </button>
                  </>
                )}
              </div>
            ))}
          </ResourceSection>
        </div>
      </section>
    </div>
  )
}

interface ResourceSectionProps {
  title: string
  empty: string
  count: number
  onSelectAll: () => void
  actions: React.ReactNode
  children: React.ReactNode
}

function ResourceSection({
  title,
  empty,
  count,
  onSelectAll,
  actions,
  children,
}: ResourceSectionProps) {
  const hasChildren = Array.isArray(children) ? children.length > 0 : Boolean(children)
  return (
    <section className="resource-section">
      <div className="resource-section-heading">
        <h3>{title}</h3>
        <button type="button" disabled={!hasChildren} onClick={onSelectAll}>
          全选当前范围
        </button>
      </div>
      <div className="resource-list">
        {hasChildren ? children : <p>{empty}</p>}
      </div>
      <footer>
        <span>已选 {count} 项</span>
        <div>{actions}</div>
      </footer>
    </section>
  )
}
