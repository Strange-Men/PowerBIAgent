/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_RUNTIME_MODE?: 'mock' | 'real'
  readonly VITE_SEMANTIC_MODEL_KEY?: string
  readonly VITE_SEMANTIC_MODEL_LABEL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
