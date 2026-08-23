import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { reportTemplateOptions } from '../config'
import type { CatalogOption } from '../types'
import { Composer } from './Composer'

const semanticModel: CatalogOption = {
  key: 'local_desktop_model',
  label: '当前销售模型',
  description: '当前已连接的 Power BI Desktop 模型',
  compatible: true,
  selectable: true,
  schemaDrift: false,
}

function renderComposer(options: CatalogOption[] = [semanticModel]) {
  const onSend = vi.fn().mockResolvedValue(undefined)
  const onSemanticModelChange = vi.fn()
  const onReportTemplateChange = vi.fn()
  render(
    <Composer
      sending={false}
      semanticModel={options[0] ?? null}
      semanticModelOptions={options}
      loadingSemanticModels={false}
      semanticModelError={options.length === 0 ? '当前没有可用数据模型。' : null}
      reportTemplate={null}
      onSemanticModelChange={onSemanticModelChange}
      onReportTemplateChange={onReportTemplateChange}
      onSend={onSend}
    />,
  )
  return { onSend, onSemanticModelChange, onReportTemplateChange }
}

describe('Composer menus and sending', () => {
  it('keeps a truly incompatible model visible and disables sending', () => {
    render(
      <Composer
        sending={false}
        semanticModel={{ ...semanticModel, compatible: false, selectable: false }}
        semanticModelOptions={[{ ...semanticModel, compatible: false, selectable: false }]}
        loadingSemanticModels={false}
        semanticModelError={null}
        semanticModelCompatibilityNotice="当前模型已连接，但缺少 PowerBIAgent 当前分析所需的部分业务字段或指标。"
        reportTemplate={null}
        onSemanticModelChange={vi.fn()}
        onReportTemplateChange={vi.fn()}
        onSend={vi.fn()}
      />,
    )
    fireEvent.change(screen.getByLabelText('询问你的 Power BI 数据'), { target: { value: '查询销售额' } })
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled()
    expect(screen.getByText(/当前模型已连接，但缺少/)).toBeInTheDocument()
  })

  it('allows sending when only the schema fingerprint drifted', () => {
    const drifted = { ...semanticModel, schemaDrift: true }
    const { onSend } = renderComposer([drifted])
    fireEvent.change(screen.getByLabelText('询问你的 Power BI 数据'), {
      target: { value: '按区域列出销售额' },
    })
    const send = screen.getByRole('button', { name: '发送' })
    expect(send).toBeEnabled()
    fireEvent.click(send)
    expect(onSend).toHaveBeenCalledWith('按区域列出销售额')
  })

  it('opens the grouped plus menu and maps the template selection', () => {
    const { onReportTemplateChange } = renderComposer()
    fireEvent.click(screen.getByRole('button', { name: '打开数据与报表选项' }))

    expect(screen.getByText('数据模型')).toBeInTheDocument()
    expect(screen.getByText('报表模板')).toBeInTheDocument()
    expect(screen.queryByText('不使用模板')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /销售分析报告/ }))
    expect(onReportTemplateChange).toHaveBeenCalledWith(reportTemplateOptions[0])
  })

  it('allows a selected template to be cleared without creating a no-template mode', () => {
    const onReportTemplateChange = vi.fn()
    render(
      <Composer
        sending={false}
        semanticModel={semanticModel}
        semanticModelOptions={[semanticModel]}
        loadingSemanticModels={false}
        semanticModelError={null}
        reportTemplate={reportTemplateOptions[0]}
        onSemanticModelChange={vi.fn()}
        onReportTemplateChange={onReportTemplateChange}
        onSend={vi.fn().mockResolvedValue(undefined)}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '打开数据与报表选项' }))
    fireEvent.click(screen.getByRole('button', { name: /销售分析报告/ }))
    expect(onReportTemplateChange).toHaveBeenCalledWith(null)
  })

  it('keeps a real DeepSeek-only selector interaction', () => {
    renderComposer()
    fireEvent.click(screen.getByRole('button', { name: /DeepSeek/ }))

    expect(screen.getByRole('listbox', { name: '选择模型' })).toBeInTheDocument()
    expect(screen.getAllByText('DeepSeek').length).toBeGreaterThan(1)
    expect(screen.queryByText('Mock')).not.toBeInTheDocument()
    expect(screen.queryByText('GPT-5.6')).not.toBeInTheDocument()
  })

  it('disables empty submit and sends non-empty content', () => {
    const { onSend } = renderComposer()
    const send = screen.getByRole('button', { name: '发送' })
    expect(send).toBeDisabled()

    fireEvent.change(screen.getByLabelText('询问你的 Power BI 数据'), {
      target: { value: '只看华南' },
    })
    expect(send).toBeEnabled()
    fireEvent.click(send)
    expect(onSend).toHaveBeenCalledWith('只看华南')
  })

  it('shows the discovery empty state and cannot send without a model', () => {
    const { onSend } = renderComposer([])
    fireEvent.change(screen.getByLabelText('询问你的 Power BI 数据'), {
      target: { value: '查询销售额' },
    })
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled()
    expect(screen.getByText('当前没有可用数据模型。')).toBeInTheDocument()
    expect(onSend).not.toHaveBeenCalled()
  })

  it('shows a safe Desktop disconnected state without internal diagnostics', () => {
    render(
      <Composer
        sending={false}
        semanticModel={null}
        semanticModelOptions={[]}
        loadingSemanticModels={false}
        semanticModelError="Power BI Desktop 未连接，请先打开一个 PBIX 文件。"
        reportTemplate={null}
        onSemanticModelChange={vi.fn()}
        onReportTemplateChange={vi.fn()}
        onSend={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(
      screen.getByText('Power BI Desktop 未连接，请先打开一个 PBIX 文件。'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/connectionstring|stack|mcp_protocol/i)).not.toBeInTheDocument()
  })
})
