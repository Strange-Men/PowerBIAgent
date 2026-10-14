import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, newCloudChat, readCloudCatalog, readCloudConversation, readCloudHistory, readCloudProfiles, readCloudReports, readCloudStatus, readCloudTemplates, restoreCloudChat, selectCloudModel, sendCloudChat } from '../api/client'
import { chatResponseToMessage, historyItemToMessages } from '../api/adapters'
import type { CloudCatalog, CloudWorkspaceStatus } from '../cloudTypes'
import type { AccountActions, AuthSession, CatalogOption, ConversationMessage, ConversationReportItem, ConversationSummary, LLMProfileOption } from '../types'
import { Sidebar } from './Sidebar'
import { Composer } from './Composer'
import { ConversationView } from './ConversationView'
import { cloudDenialMessage, publicFailureMessage } from '../failure'
import { listCloudConversations, listCloudReports, mutateCloudResource, type CloudResourceAction } from '../api/client'
import type { BatchOperationResult } from '../types'

export function CloudWorkspace({ session, onAuthInvalid, account, sessionCheckError=null, collapsed=false, onToggle=() => {} }: {
  session: AuthSession; onAuthInvalid: () => void; account?: AccountActions; sessionCheckError?: string | null; collapsed?: boolean; onToggle?: () => void
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
  const [messages,setMessages]=useState<ConversationMessage[]>([])
  const [sending,setSending]=useState(false)
  const [restored,setRestored]=useState(false)
  const [recent,setRecent]=useState<ConversationSummary[]>([])
  const [reports,setReports]=useState<ConversationReportItem[]>([])
  const generation = useRef(0)
  const serverGeneration = useRef(0)
  const active = useRef<AbortController | null>(null)

  const begin = useCallback(() => {
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    return { controller, current: ++generation.current }
  }, [])

  const clearConversation=() => { setMessages([]); setSending(false); setRestored(false) }

  const loadResources=useCallback(async (controller: AbortController,current: number) => {
    const [history,artifacts]=await Promise.all([readCloudHistory(controller.signal),readCloudReports(controller.signal)])
    if (current!==generation.current) return
    setRecent(history.items.slice(0,8)); setReports(artifacts.items.slice(0,8))
    return history.items
  },[])

  const failure = useCallback((caught: unknown, selection: boolean) => {
    if (caught instanceof ApiError && [401,403].includes(caught.status)) {
      generation.current++; active.current?.abort()
      setMessages([]); setRecent([]); setReports([]); setStatus(null); setSending(false); setRestored(false)
      setTemplates([]); setTemplate(null)
      setLoading(false); setTemplatesLoading(false)
    }
    if (caught instanceof ApiError && caught.status === 401) onAuthInvalid()
    setError(caught instanceof ApiError && caught.denialReason ? cloudDenialMessage(caught.denialReason)
      : caught instanceof ApiError && caught.failure ? publicFailureMessage(caught.failure)
      : caught instanceof ApiError && caught.status===0 ? '无法连接到 PowerBIAgent 服务，请检查网络后重试。'
      : selection ? '当前模型暂不可访问，请刷新目录后重新选择。' : '暂时无法加载数据模型，请重试。')
  }, [onAuthInvalid])

  const resourceLoaders=useMemo(()=>({
    conversations:async (resourceStatus: 'active' | 'archived',cursor?: string) => {
      const current=generation.current
      try {
        const page=await listCloudConversations(resourceStatus,20,cursor)
        if (current!==generation.current) throw new ApiError('资源请求已失效。',409)
        return page
      } catch (caught) { if (current===generation.current) failure(caught,true); throw caught }
    },
    reports:async (resourceStatus: 'active' | 'archived',cursor?: string) => {
      const current=generation.current
      try {
        const page=await listCloudReports(resourceStatus,20,cursor)
        if (current!==generation.current) throw new ApiError('资源请求已失效。',409)
        return page
      } catch (caught) { if (current===generation.current) failure(caught,true); throw caught }
    },
  }),[failure])

  const search=async (query: string) => {
    const current=generation.current
    try {
      const page=await listCloudConversations('active',50,undefined,query)
      if (current!==generation.current) throw new ApiError('搜索请求已失效。',409)
      return page.items
    } catch (caught) { if (current===generation.current) failure(caught,true); throw caught }
  }

  const mutate=async (kind: 'history' | 'reports',id: string,action: CloudResourceAction,title?: string) => {
    if (!session.csrf_token) throw new ApiError('请重新登录。',401)
    if (sending) throw new ApiError('对话仍在分析，请稍后再管理资源。',409)
    const {controller,current}=begin()
    try {
      const result=await mutateCloudResource(kind,id,action,serverGeneration.current,session.csrf_token,title,controller.signal)
      if (current!==generation.current) throw new ApiError('资源请求已失效。',409)
      const next=result.workspace_status
      serverGeneration.current=next.generation
      if (next.conversation_id!==status?.conversation_id) clearConversation()
      setStatus(next)
      if (action==='rename') {
        if (kind==='history') setRecent(items=>items.map(item=>item.conversation_id===id ? {...item,title} : item))
        else setReports(items=>items.map(item=>item.report_id===id ? {...item,display_title:title} : item))
      }
      if (action==='delete' && kind==='reports') {
        setReports(items=>items.filter(item=>item.report_id!==id))
        setMessages(items=>items.map(item=>item.role==='assistant' && item.report?.report_id===id
          ? {...item,report:{...item.report,availability_status:'deleted'}} : item))
      }
      // The server has committed the operation. Projection reads must not
      // turn that acknowledgement into a failed/retryable deletion.
      const synchronize = async () => {
        // Reread the current transcript to project report tombstones and titles.
        if (next.conversation_id && next.conversation_id===status?.conversation_id && messages.length) {
          const page=await readCloudConversation(next.conversation_id,controller.signal)
          if (current!==generation.current) throw new ApiError('资源请求已失效。',409)
          setMessages(page.items.flatMap(historyItemToMessages))
        }
        await loadResources(controller,current)
      }
      void synchronize().catch(caught => {
        if (current===generation.current) failure(caught,true)
      })
    } catch (caught) { if (current===generation.current) failure(caught,true); throw caught }
  }

  const bulk=async (kind: 'history' | 'reports',ids: string[],action: CloudResourceAction): Promise<BatchOperationResult> => {
    const result: BatchOperationResult={succeededIds:[],failed:[]}
    for (const id of ids) {
      try { await mutate(kind,id,action); result.succeededIds.push(id) }
      catch (caught) {
        result.failed.push({id,reason:'操作未完成，请重新加载资源。'})
        if (caught instanceof ApiError && [401,403,409].includes(caught.status)) {
          for (const remaining of ids.slice(result.succeededIds.length+result.failed.length)) {
            result.failed.push({id:remaining,reason:'资源授权已失效，请重新加载。'})
          }
          break
        }
      }
    }
    return result
  }

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
      if (nextStatus.execution_ready) {
        const history=await loadResources(controller,current)
        if (current!==generation.current) return
        if (nextStatus.conversation_id && history?.some(item=>item.conversation_id===nextStatus.conversation_id)) {
          const page=await readCloudConversation(nextStatus.conversation_id,controller.signal)
          if (current!==generation.current) return
          if (page.conversation_id!==nextStatus.conversation_id) throw new Error('History mismatch')
          setMessages(page.items.flatMap(historyItemToMessages)); setRestored(true)
        }
      }
      if (nextStatus.selected_model_key && models.value.items.some(item => item.key === nextStatus.selected_model_key)) {
        setTemplatesLoading(true)
        await loadTemplates(controller, current)
      }
    } catch (caught) {
      if (current !== generation.current) return
      setCatalog(null); setStatus(null); setTemplates([]); setTemplate(null)
      clearConversation(); setRecent([]); setReports([])
      if (caught instanceof ApiError && caught.status === 401) { setProfiles([]); setProfile(null) }
      failure(caught, false)
    } finally {
      if (current === generation.current) { setLoading(false); setTemplatesLoading(false) }
    }
  }, [begin, failure, loadTemplates, loadResources])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    const changed = () => {
      setLoading(true); setStatus(null); setTemplate(null); setTemplates([]); setTemplateError(null)
      clearConversation(); setRecent([]); setReports([])
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
    clearConversation(); setRecent([]); setReports([])
    await load()
  }

  const choose = async (option: CatalogOption) => {
    if (!session.csrf_token || !catalog?.items.some(item => item.key === option.key)) return
    const { controller, current } = begin()
    clearConversation()
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

  const changeConversation=async (id?: string) => {
    if (!status?.execution_ready || !session.csrf_token) return
    const {controller,current}=begin()
    clearConversation(); setError(null); setTemplates([]); setTemplate(null); setTemplatesLoading(true)
    try {
      const next=id ? await restoreCloudChat(id,serverGeneration.current,session.csrf_token,controller.signal)
        : await newCloudChat(serverGeneration.current,session.csrf_token,controller.signal)
      if (current!==generation.current) return
      serverGeneration.current=next.generation; setStatus(next)
      if (id) {
        const page=await readCloudConversation(id,controller.signal)
        if (current!==generation.current) return
        if (page.conversation_id!==id) throw new Error('History mismatch')
        setMessages(page.items.flatMap(historyItemToMessages)); setRestored(true)
      }
      await loadTemplates(controller,current)
    } catch (caught) {
      if (current!==generation.current) return
      clearConversation(); setStatus(null); failure(caught,true)
    } finally { if (current===generation.current) setTemplatesLoading(false) }
  }

  const send=async (content: string) => {
    if (!status?.execution_ready || !status.conversation_id || !session.csrf_token || sending) return
    const conversation=status.conversation_id
    const {controller,current}=begin()
    const requestId=crypto.randomUUID()
    setSending(true); setError(null)
    setMessages(previous=>[...previous,{id:`user-${requestId}`,role:'user',content}])
    try {
      const response=await sendCloudChat({message:content,request_id:requestId,expected_generation:serverGeneration.current,
        llm_profile_key:profile?.profile_key,report_template_key:template?.key},session.csrf_token,controller.signal)
      if (current!==generation.current) return
      if (response.conversation_id!==conversation || response.request_id!==requestId) throw new Error('Response mismatch')
      setMessages(previous=>[...previous,chatResponseToMessage(response)])
      await loadResources(controller,current)
    } catch (caught) {
      if (current!==generation.current) return
      if (caught instanceof ApiError && [401,403,409].includes(caught.status)) {
        clearConversation(); setStatus(null); setRecent([]); setReports([])
      }
      failure(caught,true)
    } finally { if (current===generation.current) setSending(false) }
  }

  const options: CatalogOption[] = (catalog?.items || []).map(item => ({key:item.key,
    label:item.display_name, description:item.workspace_display_name, compatible:true, selectable:true}))
  const selected = options.find(item => item.key === status?.selected_model_key) || null
  const notice = loading ? '正在加载可访问的云端模型…'
    : error || sessionCheckError || (catalog?.status === 'partial' ? '已显示可访问模型；部分模型可能未包含在目录中。'
      + (catalog.authorization_scope_complete === false && (catalog.unverified_count || 0) > 0
        ? `还有 ${catalog.unverified_count} 个模型尚未验证，请刷新目录后重试。` : '')
      : catalog?.status === 'forbidden' ? '已登录；当前账号无法读取已批准的模型目录，请切换账号或联系管理员。'
      : catalog?.status === 'error' ? '数据模型目录暂不可用，请刷新重试。'
      : selected && !status?.execution_ready ? cloudDenialMessage('cloud_execution_blocked')
      : selected ? '已选择当前账号可访问的数据模型。'
      : !options.length ? '当前没有发现可访问的数据模型。' : '请选择一个数据模型开始。')
  const executionBlocked = !status?.execution_ready ? '数据问答暂不可用，请稍后重试。' : null

  const content=<>
    <ConversationView messages={messages} sending={sending} loadingConversation={templatesLoading} restored={restored}
      welcomeDescription="请选择当前账号可访问的云端模型。" />
    <Composer key={status?.conversation_id || 'cloud-unselected'} sending={sending} semanticModel={selected} semanticModelOptions={options}
      statusNotice={<div className="cloud-catalog-status">
        <p className="local-catalog-note" role="status">{notice}</p>
        {error || catalog?.status === 'error' || catalog?.status === 'forbidden'
          ? <button type="button" onClick={() => void refresh()}>重新加载数据模型</button> : null}
      </div>}
      loadingSemanticModels={loading} semanticModelError={null}
      semanticModelCompatibilityNotice={templatesLoading ? '正在验证模型访问与报表模板…'
        : selected ? executionBlocked : '请显式选择一个数据模型'}
      reportTemplate={template} reportTemplateOptions={templates} loadingReportTemplates={templatesLoading}
      reportTemplateError={templateError} llmProfile={profile} llmProfileOptions={profiles}
      loadingLLMProfiles={loading} llmProfileError={null}
      onSemanticModelChange={option => void choose(option)} onRefreshSemanticModels={refresh}
      onReportTemplateChange={setTemplate} onLLMProfileChange={setProfile}
      onSend={send}
      dataSourceKind="cloud" executionBlockedReason={executionBlocked} />
  </>
  if (!account) return content
  return <div className="app-shell">
    <Sidebar key={status?.execution_ready ? 'ready' : 'blocked'} account={account} collapsed={collapsed} onToggle={onToggle} runtimeMode="real"
      resourceLoaders={status?.execution_ready ? resourceLoaders : undefined}
      cloudExecutionReady={Boolean(status?.execution_ready)} activeConversationId={status?.conversation_id || null}
      conversations={recent} reports={reports} error={null} onNewChat={()=>void changeConversation()}
      onOpenConversation={item=>void changeConversation(item.conversation_id)} onSearch={search}
      onRename={(item,title)=>mutate('history',item.conversation_id,'rename',title)}
      onArchive={item=>mutate('history',item.conversation_id,'archive')} onRestore={item=>mutate('history',item.conversation_id,'unarchive')}
      onDelete={item=>mutate('history',item.conversation_id,'delete')}
      onDeleteReport={item=>mutate('reports',item.report_id,'delete')} onArchiveReport={item=>mutate('reports',item.report_id,'archive')}
      onRenameReport={(item,title)=>mutate('reports',item.report_id,'rename',title)}
      onBulkDeleteConversations={items=>bulk('history',items.map(item=>item.conversation_id),'delete')}
      onBulkArchiveConversations={items=>bulk('history',items.map(item=>item.conversation_id),'archive')}
      onBulkRestoreConversations={items=>bulk('history',items.map(item=>item.conversation_id),'unarchive')}
      onBulkDeleteReports={items=>bulk('reports',items.map(item=>item.report_id),'delete')}
      onBulkArchiveReports={items=>bulk('reports',items.map(item=>item.report_id),'archive')}
      onBulkRestoreReports={items=>bulk('reports',items.map(item=>item.report_id),'unarchive')} />
    <main className="chat-main">{content}</main>
  </div>
}
