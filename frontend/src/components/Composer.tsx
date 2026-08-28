import { Check, ChevronDown, Plus, RefreshCw, Send, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { CatalogOption, LLMProfileOption } from '../types'

interface ComposerProps {
  sending: boolean
  semanticModel: CatalogOption | null
  semanticModelOptions: CatalogOption[]
  loadingSemanticModels: boolean
  semanticModelError: string | null
  semanticModelCompatibilityNotice?: string | null
  reportTemplate: CatalogOption | null
  reportTemplateOptions: CatalogOption[]
  loadingReportTemplates: boolean
  reportTemplateError: string | null
  llmProfile: LLMProfileOption | null
  llmProfileOptions: LLMProfileOption[]
  loadingLLMProfiles: boolean
  llmProfileError: string | null
  onSemanticModelChange: (option: CatalogOption) => void
  onRefreshSemanticModels: () => Promise<void>
  onReportTemplateChange: (option: CatalogOption | null) => void
  onLLMProfileChange: (option: LLMProfileOption) => void
  onSend: (content: string) => Promise<void>
}

export function Composer({
  sending,
  semanticModel,
  semanticModelOptions,
  loadingSemanticModels,
  semanticModelError,
  semanticModelCompatibilityNotice = null,
  reportTemplate,
  reportTemplateOptions,
  loadingReportTemplates,
  reportTemplateError,
  llmProfile,
  llmProfileOptions,
  loadingLLMProfiles,
  llmProfileError,
  onSemanticModelChange,
  onRefreshSemanticModels,
  onReportTemplateChange,
  onLLMProfileChange,
  onSend,
}: ComposerProps) {
  const [value, setValue] = useState('')
  const [addMenuOpen, setAddMenuOpen] = useState(false)
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const addButtonRef = useRef<HTMLButtonElement>(null)
  const modelButtonRef = useRef<HTMLButtonElement>(null)
  const canSend =
    Boolean(value.trim()) &&
    !sending &&
    semanticModel?.compatible === true &&
    semanticModel.selectable !== false &&
    llmProfile?.available === true

  useEffect(() => {
    const closeMenus = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setAddMenuOpen(false)
        setModelMenuOpen(false)
      }
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        const wasAddOpen = addMenuOpen
        const wasModelOpen = modelMenuOpen
        setAddMenuOpen(false)
        setModelMenuOpen(false)
        if (wasAddOpen) addButtonRef.current?.focus()
        if (wasModelOpen) modelButtonRef.current?.focus()
      }
    }
    document.addEventListener('mousedown', closeMenus)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', closeMenus)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [addMenuOpen, modelMenuOpen])

  const submit = async () => {
    const content = value.trim()
    if (
      !content ||
      sending ||
      !semanticModel?.compatible ||
      semanticModel.selectable === false
      || !llmProfile?.available
    ) return
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
            <div className="menu-heading">
              <span className="menu-label">数据模型</span>
              <button
                className="catalog-refresh"
                type="button"
                disabled={loadingSemanticModels}
                aria-label="刷新数据模型"
                onClick={() => void onRefreshSemanticModels()}
              >
                <RefreshCw size={14} />
                刷新
              </button>
            </div>
            {loadingSemanticModels ? (
              <p className="menu-empty-state">正在获取当前 Desktop 模型…</p>
            ) : null}
            {!loadingSemanticModels && semanticModelOptions.length === 0 ? (
              <p className="menu-empty-state">
                {semanticModelError || '当前没有可用数据模型。'}
              </p>
            ) : null}
            {semanticModelOptions.map((option, index) => (
              <button
                className="menu-option"
                key={option.key}
                type="button"
                aria-describedby={`model-status-${index}`}
                onClick={() => {
                  onSemanticModelChange(option)
                  setAddMenuOpen(false)
                }}
              >
                <span>
                  <strong>{option.label}</strong>
                  <small id={`model-status-${index}`}>{option.description}</small>
                </span>
                {semanticModel?.key === option.key ? <Check size={16} /> : null}
              </button>
            ))}
          </div>
          <div className="menu-divider" />
          <div className="menu-group">
            <div className="menu-heading">
              <span className="menu-label">报表模板</span>
              <span className="menu-status">
                {reportTemplate ? '已选择' : '未选择'}
              </span>
            </div>
            {loadingReportTemplates ? (
              <p className="menu-empty-state">正在获取报表模板…</p>
            ) : null}
            {!loadingReportTemplates && reportTemplateOptions.length === 0 ? (
              <p className="menu-empty-state">
                {reportTemplateError || '当前没有可用报表模板。'}
              </p>
            ) : null}
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
            数据模型来自后端 Desktop discovery；模板仅提供显式选择，问题内容仍决定分析或报表意图。
          </p>
        </div>
      ) : null}

      {modelMenuOpen ? (
        <div className="composer-popover model-menu" role="listbox" aria-label="选择 AI 模型">
          {loadingLLMProfiles ? <p className="menu-empty-state">正在获取 AI 模型…</p> : null}
          {!loadingLLMProfiles && llmProfileOptions.length === 0 ? (
            <p className="menu-empty-state">{llmProfileError || '当前没有可用的 AI 模型。'}</p>
          ) : null}
          {llmProfileOptions.map((profile) => (
            <button
              className="model-option"
              type="button"
              role="option"
              key={profile.profile_key}
              disabled={!profile.available}
              aria-selected={llmProfile?.profile_key === profile.profile_key}
              onClick={() => {
                onLLMProfileChange(profile)
                setModelMenuOpen(false)
              }}
            >
              <span>
                <strong>{profile.display_name}</strong>
                <small>{profile.available ? profile.model : '当前配置不可用'}</small>
              </span>
              {llmProfile?.profile_key === profile.profile_key ? <Check size={17} /> : null}
            </button>
          ))}
        </div>
      ) : null}

      <div className="composer">
        <button
          ref={addButtonRef}
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
          ref={modelButtonRef}
          className="model-selector"
          type="button"
          aria-expanded={modelMenuOpen}
          onClick={() => {
            setModelMenuOpen((open) => !open)
            setAddMenuOpen(false)
          }}
        >
          {llmProfile?.display_name || '选择 AI 模型'}
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
      <div className={`composer-selection ${semanticModelCompatibilityNotice ? 'compatibility-warning' : ''}`} aria-live="polite">
        <span>
          {loadingSemanticModels
            ? '正在连接数据模型'
            : semanticModel?.label || semanticModelError || '当前没有可用数据模型'}
        </span>
        {reportTemplate ? (
          <span>· 已选 {reportTemplate.label}</span>
        ) : (
          <span>· 未选择报表模板</span>
        )}
        {semanticModelCompatibilityNotice ? <span>{semanticModelCompatibilityNotice}</span> : null}
      </div>
    </div>
  )
}
