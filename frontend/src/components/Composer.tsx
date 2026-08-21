import { Check, ChevronDown, Plus, Send, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { reportTemplateOptions } from '../config'
import type { CatalogOption } from '../types'

interface ComposerProps {
  sending: boolean
  semanticModel: CatalogOption | null
  semanticModelOptions: CatalogOption[]
  loadingSemanticModels: boolean
  semanticModelError: string | null
  reportTemplate: CatalogOption | null
  onSemanticModelChange: (option: CatalogOption) => void
  onReportTemplateChange: (option: CatalogOption | null) => void
  onSend: (content: string) => Promise<void>
}

export function Composer({
  sending,
  semanticModel,
  semanticModelOptions,
  loadingSemanticModels,
  semanticModelError,
  reportTemplate,
  onSemanticModelChange,
  onReportTemplateChange,
  onSend,
}: ComposerProps) {
  const [value, setValue] = useState('')
  const [addMenuOpen, setAddMenuOpen] = useState(false)
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const canSend = Boolean(value.trim()) && !sending && Boolean(semanticModel)

  useEffect(() => {
    const closeMenus = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setAddMenuOpen(false)
        setModelMenuOpen(false)
      }
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setAddMenuOpen(false)
        setModelMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', closeMenus)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', closeMenus)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [])

  const submit = async () => {
    const content = value.trim()
    if (!content || sending || !semanticModel) return
    setValue('')
    setAddMenuOpen(false)
    setModelMenuOpen(false)
    await onSend(content)
  }

  return (
    <div className="composer-wrap" ref={rootRef}>
      {addMenuOpen ? (
        <div className="composer-popover add-menu" role="dialog" aria-label="数据与报表选项">
          <div className="menu-group">
            <span className="menu-label">数据模型</span>
            {loadingSemanticModels ? (
              <p className="menu-empty-state">正在获取当前 Desktop 模型…</p>
            ) : null}
            {!loadingSemanticModels && semanticModelOptions.length === 0 ? (
              <p className="menu-empty-state">
                {semanticModelError || '当前没有可用数据模型。'}
              </p>
            ) : null}
            {semanticModelOptions.map((option) => (
              <button
                className="menu-option"
                key={option.key}
                type="button"
                onClick={() => {
                  onSemanticModelChange(option)
                  setAddMenuOpen(false)
                }}
              >
                <span>
                  <strong>{option.label}</strong>
                  <small>{option.description}</small>
                </span>
                {semanticModel?.key === option.key ? <Check size={16} /> : null}
              </button>
            ))}
          </div>
          <div className="menu-divider" />
          <div className="menu-group">
            <span className="menu-label">报表模板</span>
            {reportTemplateOptions.map((option) => (
              <button
                className="menu-option"
                key={option.key}
                type="button"
                onClick={() => {
                  onReportTemplateChange(
                    reportTemplate?.key === option.key ? null : option,
                  )
                  setAddMenuOpen(false)
                }}
              >
                <span>
                  <strong>{option.label}</strong>
                  <small>{option.description}</small>
                </span>
                {reportTemplate?.key === option.key ? <Check size={16} /> : null}
              </button>
            ))}
          </div>
          <p className="local-catalog-note">
            数据模型来自后端 Desktop discovery；模板是本地安全 catalog，仅作为本次请求 override。
          </p>
        </div>
      ) : null}

      {modelMenuOpen ? (
        <div className="composer-popover model-menu" role="listbox" aria-label="选择模型">
          <button
            className="model-option"
            type="button"
            role="option"
            aria-selected="true"
            onClick={() => setModelMenuOpen(false)}
          >
            <span>
              <strong>DeepSeek</strong>
              <small>当前可用模型</small>
            </span>
            <Check size={17} />
          </button>
        </div>
      ) : null}

      <div className="composer">
        <button
          className={`composer-icon-button ${addMenuOpen ? 'is-active' : ''}`}
          type="button"
          aria-label={addMenuOpen ? '关闭数据与报表选项' : '打开数据与报表选项'}
          aria-expanded={addMenuOpen}
          onClick={() => {
            setAddMenuOpen((open) => !open)
            setModelMenuOpen(false)
          }}
        >
          {addMenuOpen ? <X size={20} /> : <Plus size={22} />}
        </button>
        <textarea
          rows={1}
          value={value}
          disabled={sending}
          placeholder="询问你的 Power BI 数据"
          aria-label="询问你的 Power BI 数据"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void submit()
            }
          }}
        />
        <button
          className="model-selector"
          type="button"
          aria-expanded={modelMenuOpen}
          onClick={() => {
            setModelMenuOpen((open) => !open)
            setAddMenuOpen(false)
          }}
        >
          DeepSeek
          <ChevronDown size={16} />
        </button>
        <button
          className="send-button"
          type="button"
          disabled={!canSend}
          aria-label="发送"
          onClick={() => void submit()}
        >
          <Send size={18} />
        </button>
      </div>
      <div className="composer-selection" aria-live="polite">
        <span>
          {loadingSemanticModels
            ? '正在连接数据模型'
            : semanticModel?.label || semanticModelError || '当前没有可用数据模型'}
        </span>
        {reportTemplate ? <span>· {reportTemplate.label}</span> : null}
      </div>
    </div>
  )
}
