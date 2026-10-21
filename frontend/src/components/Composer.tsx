import { useTranslation } from 'react-i18next'
import { tr, publicText } from '../i18n'
import { Check, ChevronDown, Plus, RefreshCw, Send, X } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { CatalogOption, LLMProfileOption } from '../types'

interface ComposerProps {
  cloudModelPicker?: (close: () => void) => ReactNode
  statusNotice?: ReactNode
  dataSourceKind?: 'desktop' | 'cloud'
  executionBlockedReason?: string | null
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
  cloudModelPicker,
  statusNotice,
  dataSourceKind = 'desktop',
  executionBlockedReason = null,
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
  useTranslation()
  const optionLabel=(option:CatalogOption)=>option.instanceNumber
    ? tr('chat:instance',{p0:option.displayName,p1:option.instanceNumber}):publicText(option.label)
  const optionDescription=(option:CatalogOption)=>option.partialDescription
    ? tr('chat:availableDataCapabilitiesDetermineWhichSectionsCanBeGenerated',{p0:publicText(option.partialDescription)}):publicText(option.description)
  const [value, setValue] = useState('')
  const [addMenuOpen, setAddMenuOpen] = useState(false)
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const [modelFilter, setModelFilter] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const addButtonRef = useRef<HTMLButtonElement>(null)
  const modelButtonRef = useRef<HTMLButtonElement>(null)
  const canSend =
    Boolean(value.trim()) &&
    !sending &&
    semanticModel?.compatible === true &&
    semanticModel.selectable !== false &&
    !(reportTemplate && loadingReportTemplates) &&
    llmProfile?.available === true
  const filteredModels = dataSourceKind === 'cloud' && modelFilter.trim()
    ? semanticModelOptions.filter(option => option.label.toLocaleLowerCase()
      .includes(modelFilter.trim().toLocaleLowerCase())) : semanticModelOptions

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
      !content || executionBlockedReason ||
      sending ||
      !semanticModel?.compatible ||
      semanticModel.selectable === false ||
      Boolean(reportTemplate && loadingReportTemplates) ||
      !llmProfile?.available
    ) return
    setValue('')
    setAddMenuOpen(false)
    setModelMenuOpen(false)
    await onSend(content)
  }

  return (
    <div className="composer-wrap" ref={rootRef}>
      {addMenuOpen ? (
        <div className="composer-popover add-menu" role="dialog" aria-label={tr('composer:dataAndReportOptions')}>
          {cloudModelPicker ? cloudModelPicker(() => setAddMenuOpen(false)) : <div className="menu-group">
            <div className="menu-heading">
              <span className="menu-label">{tr('composer:dataModel')}</span>
              <button
                className="catalog-refresh"
                type="button"
                disabled={loadingSemanticModels}
                aria-label={tr('composer:refreshDataModels')}
                onClick={() => void onRefreshSemanticModels()}
              >
                <RefreshCw size={14} />
                {tr('composer:refresh')}</button>
            </div>
            {dataSourceKind === 'cloud' && semanticModelOptions.length > 1 ? (
              <input className="catalog-filter" type="search" aria-label={tr('composer:filterDataModels')}
                placeholder={tr('composer:filterModelsByName')} maxLength={200} value={modelFilter}
                onChange={event => setModelFilter(event.target.value)} />
            ) : null}
            {loadingSemanticModels ? (
              <p className="menu-empty-state">{dataSourceKind === 'cloud' ? tr('composer:retrievingCloudDataModels') : tr('composer:retrievingTheCurrentDesktopModels')}</p>
            ) : null}
            {!loadingSemanticModels && semanticModelOptions.length === 0 ? (
              <p className="menu-empty-state">
                {semanticModelError || tr('composer:noDataModelsAreAvailable')}
              </p>
            ) : null}
            {!loadingSemanticModels && semanticModelOptions.length > 0 && filteredModels.length === 0 ? (
              <p className="menu-empty-state">{tr('composer:noMatchingModelsTryAnotherSearch')}</p>
            ) : null}
            {filteredModels.map((option, index) => (
              <button
                className="menu-option"
                key={option.key}
                type="button"
                aria-describedby={`model-status-${index}`}
                disabled={loadingSemanticModels || option.selectable === false}
                onClick={() => {
                  onSemanticModelChange(option)
                  setAddMenuOpen(false)
                }}
              >
                <span>
                  <strong>{optionLabel(option)}</strong>
                  <small id={`model-status-${index}`}>{optionDescription(option)}</small>
                </span>
                {semanticModel?.key === option.key ? <Check size={16} /> : null}
              </button>
            ))}
          </div>}
          <div className="menu-divider" />
          <div className="menu-group">
            <div className="menu-heading">
              <span className="menu-label">{tr('composer:reportTemplate')}</span>
              <span className="menu-status">
                {reportTemplate ? tr('composer:selected') : tr('composer:notSelected')}
              </span>
            </div>
            {loadingReportTemplates ? (
              <p className="menu-empty-state">{tr('composer:retrievingReportTemplates')}</p>
            ) : null}
            {!loadingReportTemplates && reportTemplateOptions.length === 0 ? (
              <p className="menu-empty-state">
                {reportTemplateError || (executionBlockedReason
                  ? tr('composer:noReportTemplatesAreAvailableForThisModel')
                  : tr('composer:noReportTemplatesMatchThisModelYouCanStill'))}
              </p>
            ) : null}
            {reportTemplateOptions.map((option) => (
              <button
                className="menu-option"
                key={option.key}
                type="button"
                disabled={!option.compatible || option.selectable === false}
                onClick={() => {
                  if (!option.compatible || option.selectable === false) return
                  onReportTemplateChange(
                    reportTemplate?.key === option.key ? null : option,
                  )
                  setAddMenuOpen(false)
                }}
              >
                <span>
                  <strong>{optionLabel(option)}</strong>
                  <small>{optionDescription(option)}</small>
                </span>
                {reportTemplate?.key === option.key ? <Check size={16} /> : null}
              </button>
            ))}
          </div>
          <p className="local-catalog-note">
            {dataSourceKind === 'cloud' ? tr('composer:onlyModelsAccessibleToThisAccountAreShownSelect') : tr('composer:modelsAreDiscoveredFromDesktopChooseATemplateExplicitly')}
          </p>
        </div>
      ) : null}

      {modelMenuOpen ? (
        <div className="composer-popover model-menu" role="listbox" aria-label={tr('composer:chooseAnAiModel')}>
          {loadingLLMProfiles ? <p className="menu-empty-state">{tr('composer:retrievingAiModels')}</p> : null}
          {!loadingLLMProfiles && llmProfileOptions.length === 0 ? (
            <p className="menu-empty-state">{llmProfileError || tr('composer:noAiModelsAreAvailable')}</p>
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
                <small>{profile.available ? profile.model : tr('composer:thisConfigurationIsUnavailable')}</small>
              </span>
              {llmProfile?.profile_key === profile.profile_key ? <Check size={17} /> : null}
            </button>
          ))}
        </div>
      ) : null}

      {statusNotice}
      <div className="composer">
        <button
          ref={addButtonRef}
          className={`composer-icon-button ${addMenuOpen ? 'is-active' : ''}`}
          type="button"
          aria-label={addMenuOpen ? tr('composer:closeDataAndReportOptions') : tr('composer:openDataAndReportOptions')}
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
          placeholder={tr('composer:askAboutYourPowerBiData')}
          aria-label={tr('composer:askAboutYourPowerBiData')}
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
          {llmProfile?.display_name || tr('composer:chooseAnAiModel')}
          <ChevronDown size={16} />
        </button>
        <button
          className="send-button"
          type="button"
          disabled={!canSend || Boolean(executionBlockedReason)}
          aria-label={tr('composer:send')}
          onClick={() => void submit()}
        >
          <Send size={18} />
        </button>
      </div>
      <div className={`composer-selection ${semanticModelCompatibilityNotice ? 'compatibility-warning' : ''}`} aria-live="polite">
        <span>
          {loadingSemanticModels
            ? tr('composer:connectingToTheDataModel')
            : (semanticModel ? optionLabel(semanticModel) : null) || semanticModelError || (dataSourceKind === 'cloud' && (semanticModelOptions.length || cloudModelPicker)
              ? tr('composer:selectACloudDataModel') : tr('composer:noDataModelsAvailable'))}
        </span>
        {reportTemplate ? (
          <span>{tr('composer:selectedTemplate', {name:optionLabel(reportTemplate)})}</span>
        ) : (
          <span>{tr('composer:noReportTemplateSelected')}</span>
        )}
        {semanticModelCompatibilityNotice ? <span>{publicText(semanticModelCompatibilityNotice)}</span> : null}
      </div>
    </div>
  )
}
