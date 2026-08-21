import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { defaultSemanticModel, reportTemplateOptions } from '../config'
import { Composer } from './Composer'

function renderComposer() {
  const onSend = vi.fn().mockResolvedValue(undefined)
  const onSemanticModelChange = vi.fn()
  const onReportTemplateChange = vi.fn()
  render(
    <Composer
      sending={false}
      semanticModel={defaultSemanticModel}
      reportTemplate={null}
      onSemanticModelChange={onSemanticModelChange}
      onReportTemplateChange={onReportTemplateChange}
      onSend={onSend}
    />,
  )
  return { onSend, onSemanticModelChange, onReportTemplateChange }
}

describe('Composer menus and sending', () => {
  it('opens the grouped plus menu and maps the template selection', () => {
    const { onReportTemplateChange } = renderComposer()
    fireEvent.click(screen.getByRole('button', { name: '打开数据与报表选项' }))

    expect(screen.getByText('数据模型')).toBeInTheDocument()
    expect(screen.getByText('报表模板')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /销售分析报告/ }))
    expect(onReportTemplateChange).toHaveBeenCalledWith(reportTemplateOptions[0])
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
})
