import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AssistantMessage } from './AssistantMessage'

describe('AssistantMessage dynamic rendering', () => {
  it('renders verified metric, table, and bar blocks from one referenced dataset', () => {
    render(
      <AssistantMessage
        message={{
          id: 'structured-1',
          role: 'assistant',
          kind: 'answer',
          content: '按区域对比如下。',
          presentation: {
            version: 1,
            datasets: [{
              result_id: 'result-1',
              verified_fact_set_id: 'facts-1',
              semantic_model_key: 'desktop-model',
              source_mode: 'real',
              columns: ['区域', '销售额'],
              rows: [['华东', 120], ['华南', 80]],
              row_count: 2,
              truncated: false,
            }],
            blocks: [
              { type: 'text', content: '按区域对比如下。' },
              { type: 'metric', data_reference: 'result-1', label: '最高示例值', value_field: '销售额', row_index: 0 },
              { type: 'table', data_reference: 'result-1', title: '区域结果' },
              { type: 'chart', data_reference: 'result-1', visual_type: 'bar', title: '区域对比', x_field: '区域', y_field: '销售额' },
            ],
          },
        }}
      />,
    )

    expect(screen.getByText('最高示例值')).toBeInTheDocument()
    expect(screen.getByRole('table')).toHaveTextContent('华东')
    expect(screen.getByLabelText('区域对比柱状图')).toBeInTheDocument()
  })

  it('renders a line chart for a backend line ChartSpec reference', () => {
    render(
      <AssistantMessage
        message={{
          id: 'structured-line', role: 'assistant', kind: 'answer', content: '趋势如下。',
          presentation: {
            version: 1,
            datasets: [{
              result_id: 'trend', verified_fact_set_id: 'facts-trend', semantic_model_key: 'desktop-model', source_mode: 'real',
              columns: ['月份', '销售额'], rows: [['2026-01', 10], ['2026-02', 20]], row_count: 2, truncated: false,
            }],
            blocks: [{ type: 'chart', data_reference: 'trend', visual_type: 'line', title: '销售趋势', x_field: '月份', y_field: '销售额' }],
          },
        }}
      />,
    )
    expect(screen.getByLabelText('销售趋势折线图')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '销售额随月份变化' })).toBeInTheDocument()
  })

  it('renders backend display bindings and formatted values without changing canonical fields', () => {
    render(
      <AssistantMessage
        message={{
          id: 'localized', role: 'assistant', kind: 'answer', content: '该期间销售额在 2025年1月达到最高点。',
          presentation: {
            version: 1,
            datasets: [{
              result_id: 'localized-result',
              verified_fact_set_id: 'localized-facts',
              semantic_model_key: 'desktop-model',
              source_mode: 'real',
              columns: ['Facts[Year Month]', '[Revenue]'],
              rows: [['2025-01-01T00:00:00', 6943997.509999986]],
              display_fields: [
                {
                  canonical_field: 'Facts[Year Month]', object_identity: 'field:Facts:Year Month', object_type: 'field',
                  canonical_name: 'Year Month', locale: 'zh-CN', display_name: '月份', source: 'model_glossary',
                  schema_identity: 'b'.repeat(64), format_kind: 'month',
                },
                {
                  canonical_field: '[Revenue]', object_identity: 'measure:Facts:Revenue', object_type: 'measure',
                  canonical_name: 'Revenue', locale: 'zh-CN', display_name: '收入', source: 'bounded_translation',
                  schema_identity: 'b'.repeat(64), format_kind: 'amount',
                },
              ],
              formatted_rows: [['2025年1月', '6,943,997.51']],
              row_count: 1,
              truncated: false,
            }],
            blocks: [{ type: 'table', data_reference: 'localized-result', title: '查询明细' }],
          },
        }}
      />,
    )

    const table = screen.getByRole('table')
    expect(table).toHaveTextContent('月份')
    expect(table).toHaveTextContent('收入')
    expect(table).toHaveTextContent('2025年1月')
    expect(table).toHaveTextContent('6,943,997.51')
    expect(table).not.toHaveTextContent('2025-01-01T00:00:00')
    expect(table).not.toHaveTextContent('Facts[Year Month]')
  })

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

  it('renders a deleted report tombstone without view or download actions', () => {
    render(
      <AssistantMessage
        message={{
          id: 'deleted-report',
          role: 'assistant',
          kind: 'answer',
          content: '曾生成报表。',
          report: {
            report_id: 'report-deleted',
            template_key: 'sales_report',
            contract_version: '2.0',
            view_reference: '',
            download_reference: '',
            content_type: 'text/html; charset=utf-8',
            content_hash: '',
            display_title: '区域销售报告',
            availability_status: 'deleted',
          },
        }}
      />,
    )

    expect(screen.getByLabelText('已删除报表')).toHaveTextContent('区域销售报告')
    expect(screen.getByText('此报表已删除')).toBeInTheDocument()
    expect(screen.getByText('此文件已不可查看或下载')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
