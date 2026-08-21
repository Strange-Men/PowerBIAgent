import type { CatalogOption, RuntimeMode } from './types'

const configuredRuntimeMode = import.meta.env.VITE_RUNTIME_MODE

export const initialRuntimeMode: RuntimeMode =
  configuredRuntimeMode === 'mock' ? 'mock' : 'real'

export const reportTemplateOptions: readonly CatalogOption[] = [
  {
    key: 'sales_report',
    label: '销售分析报告',
    description: '固定安全 HTML 模板',
  },
]

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
