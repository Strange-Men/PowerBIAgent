import type { CatalogOption, RuntimeMode } from './types'

const configuredRuntimeMode = import.meta.env.VITE_RUNTIME_MODE

export const runtimeMode: RuntimeMode =
  configuredRuntimeMode === 'mock' ? 'mock' : 'real'

const defaultSemanticModelKey =
  runtimeMode === 'mock' ? 'mock_sales_model' : 'local_desktop_model'

export const semanticModelOptions: readonly CatalogOption[] = [
  {
    key: import.meta.env.VITE_SEMANTIC_MODEL_KEY || defaultSemanticModelKey,
    label: import.meta.env.VITE_SEMANTIC_MODEL_LABEL || 'Power BI 销售数据',
    description: '本地配置的数据模型',
  },
]

export const reportTemplateOptions: readonly CatalogOption[] = [
  {
    key: 'sales_report',
    label: '销售分析报告',
    description: '固定安全 HTML 模板',
  },
]

export const defaultSemanticModel = semanticModelOptions[0]

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
