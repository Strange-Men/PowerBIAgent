import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { i18n, normalizeLocale, setLocale,publicText,resources } from './i18n'
import { LanguageSwitch } from './components/LanguageSwitch'
import { ConversationView } from './components/ConversationView'
import { I18nextProvider } from 'react-i18next'
import { pseudoInstance } from './test/pseudoLocale'

afterEach(async () => { await setLocale('zh-CN'); localStorage.clear() })

it('exact locale normalization and explicit persistent preference', async () => {
  expect(normalizeLocale('en-GB')).toBe('zh-CN')
  expect(normalizeLocale('EN-us')).toBe('zh-CN')
  expect(normalizeLocale('en-US')).toBe('en-US')
  await setLocale('en-US')
  expect(localStorage.getItem('powerbiagent.locale')).toBe('en-US')
  expect(i18n.options.fallbackLng).toBe(false)
})

it('language switch updates an existing view with zero network calls', async () => {
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  render(<><LanguageSwitch /><ConversationView messages={[]} sending={false} loadingConversation={false} restored={false} /></>)
  expect(screen.getByText('今天想分析什么数据？')).toBeVisible()
  await act(async () => { fireEvent.change(screen.getByRole('combobox', {name:'语言'}), {target:{value:'en-US'}}) })
  expect(screen.getByText('What would you like to analyze today?')).toBeVisible()
  expect(screen.queryByText('今天想分析什么数据？')).not.toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
  vi.unstubAllGlobals()
})

it('test-only pseudo locale expands complete messages and preserves interpolation', () => {
  const pseudo=pseudoInstance()
  expect(pseudo.t('resources:verifiedModelCount',{count:2})).toContain('2')
  expect(pseudo.t('chat:whatWouldYouLikeToAnalyzeToday')).toMatch(/^\[!! /)
  render(<I18nextProvider i18n={pseudo}><LanguageSwitch /></I18nextProvider>)
  expect(screen.getByRole('combobox').getAttribute('aria-label')).toMatch(/^\[!! /)
  expect(i18n.options.supportedLngs).not.toContain('en-XA')
})

it.each(['zh-CN','en-US'] as const)('projects code-owned clarification text without changing its source in %s',async locale=>{
  await setLocale(locale)
  const original=resources['zh-CN'].errors.clarification_member_no_match
  expect(publicText(original)).toBe(resources[locale].errors.clarification_member_no_match)
  expect(original).toBe(resources['zh-CN'].errors.clarification_member_no_match)
})
