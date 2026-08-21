import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AssistantMessage } from './AssistantMessage'

describe('AssistantMessage dynamic rendering', () => {
  it('renders text only when no report artifact exists', () => {
    render(
      <AssistantMessage
        message={{
          id: 'answer-1',
          role: 'assistant',
          kind: 'answer',
          content: '这是一个普通数据回答。',
        }}
      />,
    )

    expect(screen.getByText('这是一个普通数据回答。')).toBeInTheDocument()
    expect(screen.queryByLabelText('HTML 报表附件')).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('renders backend report view and download references when provided', () => {
    render(
      <AssistantMessage
        message={{
          id: 'report-1',
          role: 'assistant',
          kind: 'answer',
          content: '报表已生成。',
          report: {
            report_id: 'report-1',
            template_key: 'sales_report',
            contract_version: '2.0',
            view_reference: '/api/reports/report-1',
            download_reference: '/api/reports/report-1/download',
            content_type: 'text/html; charset=utf-8',
            content_hash: 'hash',
          },
        }}
      />,
    )

    expect(screen.getByLabelText('HTML 报表附件')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /查看报表/ })).toHaveAttribute(
      'href',
      '/api/reports/report-1',
    )
    expect(screen.getByRole('link', { name: /下载 HTML/ })).toHaveAttribute(
      'href',
      '/api/reports/report-1/download',
    )
  })
})
