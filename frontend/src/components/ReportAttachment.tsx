import { Download, ExternalLink, FileText } from 'lucide-react'
import type { ReportResource } from '../types'

interface ReportAttachmentProps {
  report: ReportResource
}

export function ReportAttachment({ report }: ReportAttachmentProps) {
  const deleted = report.availability_status === 'deleted'
  const title = report.display_title?.trim() || '销售分析报告'
  return (
    <section
      className={`report-attachment ${deleted ? 'report-attachment-deleted' : ''}`}
      aria-label={deleted ? '已删除报表' : 'HTML 报表附件'}
    >
      <div className="report-file-icon" aria-hidden="true">
        <FileText size={22} strokeWidth={1.7} />
      </div>
      <div className="report-file-copy">
        <strong>{title}</strong>
        <span>{deleted ? '报表已删除' : 'HTML 报表'}</span>
      </div>
      {deleted ? (
        <p className="report-tombstone-copy">此文件已不可查看或下载</p>
      ) : (
        <div className="report-actions">
          <a href={report.view_reference} target="_blank" rel="noreferrer">
            <ExternalLink size={15} />
            查看报表
          </a>
          <a href={report.download_reference} download>
            <Download size={15} />
            下载 HTML
          </a>
        </div>
      )}
    </section>
  )
}
