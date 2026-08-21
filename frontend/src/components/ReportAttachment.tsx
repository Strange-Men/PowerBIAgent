import { Download, ExternalLink, FileText } from 'lucide-react'
import type { ReportResource } from '../types'

interface ReportAttachmentProps {
  report: ReportResource
}

export function ReportAttachment({ report }: ReportAttachmentProps) {
  return (
    <section className="report-attachment" aria-label="HTML 报表附件">
      <div className="report-file-icon" aria-hidden="true">
        <FileText size={22} strokeWidth={1.7} />
      </div>
      <div className="report-file-copy">
        <strong>销售分析报告</strong>
        <span>HTML 报表</span>
      </div>
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
    </section>
  )
}
