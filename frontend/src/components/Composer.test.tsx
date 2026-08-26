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
  const onRefreshSemanticModels = vi.fn().mockResolvedValue(undefined)
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
      onRefreshSemanticModels={onRefreshSemanticModels}
      onReportTemplateChange={onReportTemplateChange}
      onSend={onSend}
    />,
  )
  return {
    onSend,
    onSemanticModelChange,
    onRefreshSemanticModels,
    onReportTemplateChange,
  }
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
        onRefreshSemanticModels={vi.fn().mockResolvedValue(undefined)}
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
    expect(screen.getByText(/生成报表前请选择模板/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /简易模板/ }))
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
        onRefreshSemanticModels={vi.fn().mockResolvedValue(undefined)}
        onReportTemplateChange={onReportTemplateChange}
        onSend={vi.fn().mockResolvedValue(undefined)}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '打开数据与报表选项' }))
    fireEvent.click(screen.getByRole('button', { name: /简易模板/ }))
    expect(onReportTemplateChange).toHaveBeenCalledWith(null)
  })

  it('does not implicitly select a report template and keeps data questions sendable', () => {
    const { onSend, onReportTemplateChange } = renderComposer()
    expect(screen.getByText(/未选择报表模板/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('询问你的 Power BI 数据'), {
      target: { value: '查询销售额' },
    })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))
    expect(onSend).toHaveBeenCalledWith('查询销售额')
    expect(onReportTemplateChange).not.toHaveBeenCalled()
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
        onRefreshSemanticModels={vi.fn().mockResolvedValue(undefined)}
        onReportTemplateChange={vi.fn()}
        onSend={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(
      screen.getByText('Power BI Desktop 未连接，请先打开一个 PBIX 文件。'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/connectionstring|stack|mcp_protocol/i)).not.toBeInTheDocument()
  })

  it('shows multiple Desktop models and allows selecting each PBIX', () => {
    const second = {
      ...semanticModel,
      key: 'local_desktop:bbbb',
      label: 'PowerBIAgent_M3_Test',
    }
    const first = {
      ...semanticModel,
      key: 'local_desktop:aaaa',
      label: 'PowerBIAgent_M3_Rich_Test',
    }
    const { onSemanticModelChange } = renderComposer([first, second])
    fireEvent.click(screen.getByRole('button', { name: '打开数据与报表选项' }))

    expect(screen.getAllByText('PowerBIAgent_M3_Rich_Test')).toHaveLength(2)
    expect(screen.getByText('PowerBIAgent_M3_Test')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /PowerBIAgent_M3_Test/ }))
    expect(onSemanticModelChange).toHaveBeenCalledWith(second)
    expect(screen.queryByText(/local_desktop:/)).not.toBeInTheDocument()
  })

  it('refreshes the Desktop catalog from the model menu', () => {
    const { onRefreshSemanticModels } = renderComposer()
    fireEvent.click(screen.getByRole('button', { name: '打开数据与报表选项' }))
    fireEvent.click(screen.getByRole('button', { name: '刷新数据模型' }))

    expect(onRefreshSemanticModels).toHaveBeenCalledOnce()
  })

  it('shows a safe stale-selection error and keeps sending disabled', () => {
    const onSend = vi.fn()
    render(
      <Composer
        sending={false}
        semanticModel={null}
        semanticModelOptions={[]}
        loadingSemanticModels={false}
        semanticModelError="当前选择的数据模型已关闭或失效，请刷新后重新选择。"
        reportTemplate={null}
        onSemanticModelChange={vi.fn()}
        onRefreshSemanticModels={vi.fn().mockResolvedValue(undefined)}
        onReportTemplateChange={vi.fn()}
        onSend={onSend}
      />,
    )
    fireEvent.change(screen.getByLabelText('询问你的 Power BI 数据'), {
      target: { value: '查询销售额' },
    })

    expect(screen.getByText(/已关闭或失效/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled()
    expect(onSend).not.toHaveBeenCalled()
  })
})
