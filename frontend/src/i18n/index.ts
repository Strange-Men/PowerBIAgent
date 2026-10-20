import { createInstance } from 'i18next'
import { initReactI18next } from 'react-i18next'
import commonZh from './locales/zh-CN/common.json'
import authZh from './locales/zh-CN/auth.json'
import chatZh from './locales/zh-CN/chat.json'
import sidebarZh from './locales/zh-CN/sidebar.json'
import composerZh from './locales/zh-CN/composer.json'
import reportsZh from './locales/zh-CN/reports.json'
import resourcesZh from './locales/zh-CN/resources.json'
import errorsZh from './locales/zh-CN/errors.json'
import commonEn from './locales/en-US/common.json'
import authEn from './locales/en-US/auth.json'
import chatEn from './locales/en-US/chat.json'
import sidebarEn from './locales/en-US/sidebar.json'
import composerEn from './locales/en-US/composer.json'
import reportsEn from './locales/en-US/reports.json'
import resourcesEn from './locales/en-US/resources.json'
import errorsEn from './locales/en-US/errors.json'

export type SupportedLocale = 'zh-CN' | 'en-US'
export function normalizeLocale(value: unknown): SupportedLocale {
  return value === 'en-US' ? 'en-US' : 'zh-CN'
}
const preferenceKey = 'powerbiagent.locale'
export function initialLocale(): SupportedLocale {
  try {
    const stored = localStorage.getItem(preferenceKey)
    if (stored !== null) return normalizeLocale(stored)
  } catch { /* Storage is optional; browser preference still applies. */ }
  return normalizeLocale(typeof navigator === 'undefined' ? null : navigator.language)
}
export const resources = {
  'zh-CN': {common:commonZh, auth:authZh, chat:chatZh, sidebar:sidebarZh, composer:composerZh, reports:reportsZh, resources:resourcesZh, errors:errorsZh},
  'en-US': {common:commonEn, auth:authEn, chat:chatEn, sidebar:sidebarEn, composer:composerEn, reports:reportsEn, resources:resourcesEn, errors:errorsEn},
}
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'common'
    resources: typeof resources['zh-CN']
    strictKeyChecks: true
  }
}
export const i18n = createInstance()
void i18n.use(initReactI18next).init({
  resources, lng:initialLocale(), supportedLngs:['zh-CN','en-US'],
  load:'currentOnly', fallbackLng:false, defaultNS:'common',
  initAsync:false, interpolation:{escapeValue:false},
  returnNull:false, returnEmptyString:false,
  // Completeness is a CI requirement. A deployment with damaged resources
  // fails closed to a neutral glyph instead of another language or a key.
  parseMissingKeyHandler:()=>'—',
})
if (typeof document!=='undefined') document.documentElement.lang=normalizeLocale(i18n.language)
export const tr = i18n.t.bind(i18n)
export async function setLocale(value: unknown): Promise<void> {
  const locale = normalizeLocale(value)
  try { localStorage.setItem(preferenceKey, locale) } catch { /* Session preference still applies. */ }
  await i18n.changeLanguage(locale)
  document.documentElement.lang = locale
}

/** Re-project a public resource message held in existing asynchronous state.
 * Only exact catalog-owned messages match; never translate user input or facts.
 */
export function publicText(value: string | null | undefined): string {
  if (!value) return value || ''
  for (const catalog of Object.values(resources)) {
    for (const [ns, entries] of Object.entries(catalog)) {
      const key = Object.entries(entries).find(([, text])=>text===value)?.[0]
      if (key) return i18n.getResource(normalizeLocale(i18n.language), ns, key) as string
    }
  }
  return value
}

/** Existing report identity is stable; locale selects only its presentation stream. */
export function reportReference(reference:string):string {
  return normalizeLocale(i18n.language)==='en-US' ? `${reference}?locale=en-US` : reference
}
