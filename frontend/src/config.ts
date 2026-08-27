import type { RuntimeMode } from './types'

const configuredRuntimeMode = import.meta.env.VITE_RUNTIME_MODE

export const initialRuntimeMode: RuntimeMode =
  configuredRuntimeMode === 'mock' ? 'mock' : 'real'

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
