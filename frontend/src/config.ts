import type { CatalogOption, RuntimeMode } from './types'

const configuredRuntimeMode = import.meta.env.VITE_RUNTIME_MODE

export const initialRuntimeMode: RuntimeMode =
  configuredRuntimeMode === 'mock' ? 'mock' : 'real'

export const reportTemplateOptions: readonly CatalogOption[] = [
  {
    key: 'sales_report',
    label: '简易模板',
    description: '适合快速查看关键指标、趋势与分类明细',
    compatible: true,
    compatibilityStatus: 'compatible',
  },
]

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
