import { useTranslation } from 'react-i18next'
import { tr, publicText, reportReference } from '../i18n'
import { Download, ExternalLink, FileText } from 'lucide-react'
import type { ReportResource } from '../types'

interface ReportAttachmentProps {
  report: ReportResource
}

export function ReportAttachment({ report }: ReportAttachmentProps) {
  useTranslation()
  const deleted = report.availability_status === 'deleted'
  const title = publicText(report.display_title?.trim()) || tr('reports:salesAnalysisReport')
  return (
    <section
      className={`report-attachment ${deleted ? 'report-attachment-deleted' : ''}`}
      aria-label={deleted ? tr('reports:deletedReport') : tr('reports:htmlReportAttachment')}
    >
      <div className="report-file-icon" aria-hidden="true">
        <FileText size={22} strokeWidth={1.7} />
      </div>
      <div className="report-file-copy">
        <strong>{title}</strong>
        <span>{deleted ? tr('reports:thisReportWasDeleted') : tr('reports:htmlReport')}</span>
      </div>
      {deleted ? (
        <p className="report-tombstone-copy">{tr('reports:thisFileCanNoLongerBeViewedOrDownloaded')}</p>
      ) : (
        <div className="report-actions">
          <a href={reportReference(report.view_reference)} target="_blank" rel="noreferrer">
            <ExternalLink size={15} />
            {tr('reports:viewReport')}</a>
          <a href={reportReference(report.download_reference)} download>
            <Download size={15} />
            {tr('reports:downloadHtml')}</a>
        </div>
      )}
    </section>
  )
}
