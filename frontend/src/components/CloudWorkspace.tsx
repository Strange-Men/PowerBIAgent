import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, readCloudCatalog, readCloudProfiles, readCloudStatus, readCloudTemplates, selectCloudModel } from '../api/client'
import type { CloudCatalog, CloudWorkspaceStatus } from '../cloudTypes'
import type { AuthSession, CatalogOption, LLMProfileOption } from '../types'
import { Composer } from './Composer'
import { ConversationView } from './ConversationView'
import { publicFailureMessage } from '../failure'

export function CloudWorkspace({ session, onAuthInvalid }: {
  session: AuthSession; onAuthInvalid: () => void
}) {
  const [catalog, setCatalog] = useState<CloudCatalog | null>(null)
  const [status, setStatus] = useState<CloudWorkspaceStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [profiles, setProfiles] = useState<LLMProfileOption[]>([])
  const [profile, setProfile] = useState<LLMProfileOption | null>(null)
  const [templates, setTemplates] = useState<CatalogOption[]>([])
  const [template, setTemplate] = useState<CatalogOption | null>(null)
  const [templatesLoading, setTemplatesLoading] = useState(false)
  const [templateError, setTemplateError] = useState<string | null>(null)
  const generation = useRef(0)
  const serverGeneration = useRef(0)
  const active = useRef<AbortController | null>(null)

  const begin = useCallback(() => {
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    return { controller, current: ++generation.current }
  }, [])

  const failure = useCallback((caught: unknown, selection: boolean) => {
    if (caught instanceof ApiError && caught.status === 401) onAuthInvalid()
    setError(caught instanceof ApiError && caught.failure ? publicFailureMessage(caught.failure)
      : selection ? '当前模型暂不可访问，请刷新目录后重新选择。' : '暂时无法加载数据模型，请重试。')
  }, [onAuthInvalid])

  const loadTemplates = useCallback(async (controller: AbortController, current: number) => {
    try {
      const nextTemplates = await readCloudTemplates(controller.signal)
      if (current !== generation.current) return
      setTemplateError(nextTemplates.reason_code === 'semantic_model_schema_unavailable'
        ? '暂时无法验证报表模板，请刷新模型后重试。' : null)
      setTemplates(nextTemplates.items.map(item => ({key:item.template_key,label:item.display_name,
        description:item.description,compatible:item.selectable,selectable:item.selectable,
        compatibilityStatus:item.compatibility_status})))
    } catch (caught) {
      if (current !== generation.current) return
      if (caught instanceof ApiError && caught.status === 401) throw caught
      setTemplates([]); setTemplate(null)
      setTemplateError(caught instanceof ApiError && caught.failure ? publicFailureMessage(caught.failure)
        : '暂时无法验证报表模板，请刷新模型后重试。')
    }
  }, [])

  const load = useCallback(async () => {
    const { controller, current } = begin()
    try {
      const [models, llms] = await Promise.allSettled([
        readCloudCatalog(controller.signal), readCloudProfiles(controller.signal),
      ])
      if (current !== generation.current) return
      if (llms.status === 'rejected' && llms.reason instanceof ApiError && llms.reason.status === 401) {
        throw llms.reason
      }
      if (llms.status === 'fulfilled') {
        setProfiles(llms.value.items)
        setProfile(previous => llms.value.items.find(item => item.profile_key === previous?.profile_key && item.available)
          || llms.value.items.find(item => item.default && item.available) || null)
      }
      if (models.status === 'rejected') throw models.reason
      const nextStatus = await readCloudStatus(controller.signal)
      if (current !== generation.current) return
      setCatalog(models.value)
      setStatus(nextStatus)
      serverGeneration.current = nextStatus.generation
      if (nextStatus.selected_model_key && models.value.items.some(item => item.key === nextStatus.selected_model_key)) {
        setTemplatesLoading(true)
        await loadTemplates(controller, current)
      }
    } catch (caught) {
      if (current !== generation.current) return
      setCatalog(null); setStatus(null); setTemplates([]); setTemplate(null)
      if (caught instanceof ApiError && caught.status === 401) { setProfiles([]); setProfile(null) }
      failure(caught, false)
    } finally {
      if (current === generation.current) { setLoading(false); setTemplatesLoading(false) }
    }
  }, [begin, failure, loadTemplates])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    const changed = () => {
      setLoading(true); setStatus(null); setTemplate(null); setTemplates([]); setTemplateError(null)
      void load()
    }
    window.addEventListener('powerbiagent-cloud-catalog-updated', changed)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('powerbiagent-cloud-catalog-updated', changed)
      generation.current += 1; active.current?.abort()
    }
  }, [load])

  const refresh = async () => {
    setLoading(true); setError(null); setStatus(null); setTemplate(null); setTemplates([]); setTemplateError(null)
    await load()
  }

  const choose = async (option: CatalogOption) => {
    if (!session.csrf_token || !catalog?.items.some(item => item.key === option.key)) return
    const { controller, current } = begin()
    setError(null); setStatus(null); setTemplate(null); setTemplates([]); setTemplateError(null); setTemplatesLoading(true)
    try {
      let nextStatus: CloudWorkspaceStatus
      try {
        nextStatus = await selectCloudModel(option.key, session.csrf_token, serverGeneration.current, controller.signal)
      } catch (caught) {
        if (!(caught instanceof ApiError) || caught.status !== 409 || current !== generation.current) throw caught
        const latest = await readCloudStatus(controller.signal)
        if (current !== generation.current) return
        nextStatus = await selectCloudModel(option.key, session.csrf_token, latest.generation, controller.signal)
      }
      if (current !== generation.current) return
      if (nextStatus.selected_model_key !== option.key) throw new Error('Selection mismatch')
      setStatus(nextStatus)
      serverGeneration.current = nextStatus.generation
      await loadTemplates(controller, current)
    } catch (caught) {
      if (current !== generation.current) return
      setStatus(null); failure(caught, true)
    } finally {
      if (current === generation.current) setTemplatesLoading(false)
    }
  }

  const options: CatalogOption[] = (catalog?.items || []).map(item => ({key:item.key,
    label:item.display_name, description:item.workspace_display_name, compatible:true, selectable:true}))
  const selected = options.find(item => item.key === status?.selected_model_key) || null
  const notice = loading ? '正在加载可访问的云端模型…'
    : error || (catalog?.status === 'partial' ? '已显示可访问模型；部分模型可能未包含在目录中。'
      + (catalog.authorization_scope_complete === false && (catalog.unverified_count || 0) > 0
        ? `还有 ${catalog.unverified_count} 个模型尚未验证，请刷新目录后重试。` : '')
      : catalog?.status === 'forbidden' ? '当前账号无法读取模型目录，请切换账号或联系管理员。'
      : catalog?.status === 'error' ? '数据模型目录暂不可用，请刷新重试。'
      : !options.length ? '当前没有发现可访问的数据模型。' : '请选择一个数据模型开始。')
  const executionBlocked = !status?.execution_ready ? '数据问答暂不可用，请稍后重试。' : null

  return <>
    <ConversationView messages={[]} sending={false} loadingConversation={false} restored={false}
      welcomeDescription="请选择当前账号可访问的云端模型。" />
    <p className="local-catalog-note" role="status">{notice}</p>
    {error || catalog?.status === 'error' || catalog?.status === 'forbidden'
      ? <button type="button" onClick={() => void refresh()}>重新加载数据模型</button> : null}
    <Composer key={status?.conversation_id || 'cloud-unselected'} sending={false} semanticModel={selected} semanticModelOptions={options}
      loadingSemanticModels={loading} semanticModelError={error}
      semanticModelCompatibilityNotice={templatesLoading ? '正在验证模型访问与报表模板…'
        : selected ? executionBlocked : '请显式选择一个数据模型'}
      reportTemplate={template} reportTemplateOptions={templates} loadingReportTemplates={templatesLoading}
      reportTemplateError={templateError} llmProfile={profile} llmProfileOptions={profiles}
      loadingLLMProfiles={loading} llmProfileError={null}
      onSemanticModelChange={option => void choose(option)} onRefreshSemanticModels={refresh}
      onReportTemplateChange={setTemplate} onLLMProfileChange={setProfile}
      onSend={async () => { throw new Error('Cloud execution is not ready') }}
      dataSourceKind="cloud" executionBlockedReason={executionBlocked} />
  </>
}
