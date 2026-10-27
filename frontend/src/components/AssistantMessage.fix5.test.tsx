import { act, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AssistantMessage } from './AssistantMessage'
import { i18n } from '../i18n'
import * as api from '../api/client'

vi.mock('../api/client', () => ({ projectPresentation: vi.fn() }))

const context = {
  mode: 'real' as const,
  cloud: true,
  csrf: 'synthetic-proof',
  generation: 1,
  conversationId: 'conversation-1',
}

describe('M6.5.2 FIX5 historical restore', () => {
  it('shows the persisted answer when a restored message has no presentation recipe', async () => {
    await i18n.changeLanguage('en-US')
    vi.mocked(api.projectPresentation).mockClear()
    render(
      <AssistantMessage
        projectionContext={context}
        message={{
          id: 'historical-answer',
          role: 'assistant',
          kind: 'answer',
          content: 'France 的销售额为 100。',
          restored: true,
        }}
      />,
    )
    expect(screen.getByText('France 的销售额为 100。')).toBeInTheDocument()
    expect(screen.queryByText(/Language switching is unavailable/)).not.toBeInTheDocument()
    expect(api.projectPresentation).not.toHaveBeenCalled()
  })

  it('keeps the persisted answer visible without a misleading notice when re-projection fails', async () => {
    await i18n.changeLanguage('en-US')
    vi.mocked(api.projectPresentation).mockRejectedValueOnce(new Error('unavailable'))
    render(
      <AssistantMessage
        projectionContext={context}
        message={{
          id: 'historical-projection',
          role: 'assistant',
          kind: 'answer',
          content: 'Original persisted answer',
          presentationAvailable: true,
          restored: true,
        }}
      />,
    )
    await waitFor(() =>
      expect(screen.getByText('Original persisted answer')).toBeInTheDocument(),
    )
    expect(screen.queryByText(/Language switching is unavailable/)).not.toBeInTheDocument()
  })

  it('reports an unavailable language switch only after the reader switches', async () => {
    await i18n.changeLanguage('zh-CN')
    vi.mocked(api.projectPresentation).mockRejectedValue(new Error('unavailable'))
    render(
      <AssistantMessage
        projectionContext={context}
        message={{
          id: 'historical-switch',
          role: 'assistant',
          kind: 'answer',
          content: 'Original persisted answer',
          presentationAvailable: true,
          restored: true,
        }}
      />,
    )
    await waitFor(() =>
      expect(screen.getByText('Original persisted answer')).toBeInTheDocument(),
    )
    expect(screen.queryByText(/Language switching is unavailable/)).not.toBeInTheDocument()
    await act(async () => { await i18n.changeLanguage('en-US') })
    await waitFor(() =>
      expect(screen.getByText(/Language switching is unavailable/)).toBeInTheDocument(),
    )
    expect(screen.getByText('Original persisted answer')).toBeInTheDocument()
  })

  it('re-localizes a persisted clarification from its catalog text', async () => {
    await i18n.changeLanguage('en-US')
    render(
      <AssistantMessage
        projectionContext={context}
        message={{
          id: 'historical-clarification',
          role: 'assistant',
          kind: 'clarification',
          content: '未能确定筛选字段，请同时说明字段和值。',
          restored: true,
        }}
      />,
    )
    expect(
      screen.getByText(
        'Unable to identify the filter field. Specify both the field and its value.',
      ),
    ).toBeInTheDocument()
  })
})
