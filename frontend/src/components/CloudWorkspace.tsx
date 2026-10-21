import { useTranslation } from 'react-i18next'
import { tr, publicText } from '../i18n'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, newCloudChat, readCloudCatalog, readCloudWorkspaces, readCloudConversation, readCloudHistory, readCloudProfiles, readCloudReports, readCloudStatus, readCloudTemplates, restoreCloudChat, selectCloudModel, sendCloudChat } from '../api/client'
import { chatResponseToMessage, historyItemToMessages } from '../api/adapters'
import type { CloudCatalog, CloudWorkspaceStatus } from '../cloudTypes'
import type { AccountActions, AuthSession, CatalogOption, ConversationMessage, ConversationReportItem, ConversationSummary, LLMProfileOption } from '../types'
import { Sidebar } from './Sidebar'
import { Composer } from './Composer'
import { ConversationView } from './ConversationView'
import { CloudCatalogPicker } from './CloudCatalogPicker'
import { cloudDenialMessage, cloudFailureAction, publicFailureMessage } from '../failure'
import { listCloudConversations, listCloudReports, mutateCloudResource, type CloudResourceAction } from '../api/client'
import type { BatchOperationResult } from '../types'
import { openCloudResourceLink } from '../api/client'
type CloudOperation = 'catalog' | 'selection' | 'chat' | 'template' | 'history' | 'report' | 'resource_mutation' | 'presentation'

export function CloudWorkspace({ session, onAuthInvalid, account, sessionCheckError=null, collapsed=false, onToggle=() => {} }: {
  session: AuthSession; onAuthInvalid: () => void; account?: AccountActions; sessionCheckError?: string | null; collapsed?: boolean; onToggle?: () => void
}) {
  useTranslation()
  const [catalog, setCatalog] = useState<CloudCatalog | null>(null)
  const [status, setStatus] = useState<CloudWorkspaceStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [noWorkspaceAccess, setNoWorkspaceAccess] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [profiles, setProfiles] = useState<LLMProfileOption[]>([])
  const [profile, setProfile] = useState<LLMProfileOption | null>(null)
  const [templates, setTemplates] = useState<CatalogOption[]>([])
  const [template, setTemplate] = useState<CatalogOption | null>(null)
  const [templatesLoading, setTemplatesLoading] = useState(false)
  const [modelSelectionLoading, setModelSelectionLoading] = useState(false)
  const [conversationRestoreLoading, setConversationRestoreLoading] = useState(false)
  const [reloadModels, setReloadModels] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [reportError, setReportError] = useState<string | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [reportsLoading, setReportsLoading] = useState(false)
  const [templateError, setTemplateError] = useState<string | null>(null)
  const [messages,setMessages]=useState<ConversationMessage[]>([])
  const [sending,setSending]=useState(false)
  const [restored,setRestored]=useState(false)
  const [recent,setRecent]=useState<ConversationSummary[]>([])
  const [reports,setReports]=useState<ConversationReportItem[]>([])
  const generation = useRef(0)
  const serverGeneration = useRef(0)
  const active = useRef<AbortController | null>(null)
  const productMode = useRef(false)

  const begin = useCallback(() => {
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    return { controller, current: ++generation.current }
  }, [])

  const clearConversation=() => { setMessages([]); setSending(false); setRestored(false) }

  const loadResources=useCallback(async (controller: AbortController,current: number,kind?: 'history'|'report') => {
    const history=kind==='report' ? Promise.resolve(undefined) : (async()=>{
      setHistoryLoading(true)
      try {
        const page=await readCloudHistory(controller.signal)
        if(current===generation.current){setRecent(page.items.slice(0,8));setHistoryError(null)}
        return page.items
      } catch(caught) {
        if(current===generation.current)setHistoryError(tr('chat:conversationHistoryIsUnavailable'))
        throw caught
      } finally {if(current===generation.current)setHistoryLoading(false)}
    })()
    const reports=kind==='history' ? Promise.resolve() : (async()=>{
      setReportsLoading(true)
      try {
        const page=await readCloudReports(controller.signal)
        if(current===generation.current){setReports(page.items.slice(0,8));setReportError(null)}
      } catch(caught) {
        if(current===generation.current)setReportError(tr('chat:reportListUnavailable'))
        throw caught
      } finally {if(current===generation.current)setReportsLoading(false)}
    })()
    const results=await Promise.allSettled([history,reports])
    if(current!==generation.current)return
    for(const result of results){
      if(result.status==='rejected' && result.reason instanceof ApiError && cloudFailureAction(result.reason)==='auth')throw result.reason
    }
    return results[0].status==='fulfilled' ? results[0].value : undefined
  },[])

  const failure = useCallback((caught: unknown, operation: CloudOperation, resourceKey?: string) => {
    const action=caught instanceof ApiError ? cloudFailureAction(caught) : 'recoverable'
    const message=caught instanceof ApiError && caught.denialReason ? cloudDenialMessage(caught.denialReason, productMode.current)
      : action==='conflict' ? tr('chat:theSessionHasChangedSynchronizingPleaseTryAgain')
      : caught instanceof ApiError && caught.failure ? publicFailureMessage(caught.failure)
      : caught instanceof ApiError && caught.status===0 ? tr('errors:cannotConnectToPowerbiagentCheckYourNetworkAndTry')
      : operation==='catalog' ? tr('chat:cannotLoadDataModelsTryAgain')
      : action==='resource' ? tr('chat:thisModelIsInaccessibleRefreshTheCatalogAndSelect')
      : tr('chat:thisRequestCouldNotBeCompletedTryAgainLater')
    if (action!=='auth' && ['history','report','presentation','resource_mutation'].includes(operation)) {
      if (operation==='history') setHistoryError(message)
      else setReportError(message)
      return
    }
    setReloadModels(operation==='catalog' || action==='resource')
    if (action==='auth') {
      generation.current++; active.current?.abort()
      setMessages([]); setRecent([]); setReports([]); setStatus(null); setSending(false); setRestored(false)
      setCatalog(null); setProfiles([]); setProfile(null); setTemplates([]); setTemplate(null)
      setLoading(false); setTemplatesLoading(false); setModelSelectionLoading(false); setConversationRestoreLoading(false)
      onAuthInvalid()
    } else if (action==='resource') {
      generation.current++; active.current?.abort()
      setSending(false); setLoading(false); setTemplatesLoading(false)
      if (resourceKey) setCatalog(previous=>previous ? {...previous,items:previous.items.filter(item=>item.key!==resourceKey)} : previous)
      if (operation!=='catalog') {
        setStatus(previous=>previous && resourceKey && previous.selected_model_key!==resourceKey ? previous : null)
        setMessages([]); setRestored(false); setTemplates([]); setTemplate(null)
      }
    } else if (action==='conflict') {
      const {controller,current}=begin()
      setSending(false); setTemplatesLoading(false)
      void readCloudStatus(controller.signal).then(next=>{
        if (current!==generation.current) return
        serverGeneration.current=next.generation
        setStatus(next)
        // A changed generation can invalidate displayed business context.
        setMessages([]); setRestored(false); setTemplates([]); setTemplate(null)
      }).catch(syncError=>{
        if (current!==generation.current) return
        if (syncError instanceof ApiError && cloudFailureAction(syncError)==='auth') {
          setCatalog(null); setStatus(null); setMessages([]); setRecent([]); setReports([])
          setTemplates([]); setTemplate(null); onAuthInvalid()
        } else setError(tr('chat:cannotSynchronizeThisSessionTryAgain'))
      })
    }
    setError(message)
  }, [onAuthInvalid,begin])
  const catalogFailure = useCallback((caught: unknown) => failure(caught, 'catalog'), [failure])

  const resourceLoaders=useMemo(()=>({
    conversations:async (resourceStatus: 'active' | 'archived',cursor?: string) => {
      const current=generation.current
      try {
        const page=await listCloudConversations(resourceStatus,20,cursor)
        if (current!==generation.current) throw new ApiError(tr('chat:thisResourceRequestIsNoLongerValid'),409)
        return page
      } catch (caught) { if (current===generation.current) failure(caught,'history'); throw caught }
    },
    reports:async (resourceStatus: 'active' | 'archived',cursor?: string) => {
      const current=generation.current
      try {
        const page=await listCloudReports(resourceStatus,20,cursor)
        if (current!==generation.current) throw new ApiError(tr('chat:thisResourceRequestIsNoLongerValid'),409)
        return page
      } catch (caught) { if (current===generation.current) failure(caught,'report'); throw caught }
    },
  }),[failure])

  const search=async (query: string) => {
    const current=generation.current
    try {
      const page=await listCloudConversations('active',50,undefined,query)
      if (current!==generation.current) throw new ApiError(tr('chat:thisSearchRequestIsNoLongerValid'),409)
      return page.items
    } catch (caught) { if (current===generation.current) failure(caught,'history'); throw caught }
  }

  const mutate=async (kind: 'history' | 'reports',id: string,action: CloudResourceAction,title?: string) => {
    if (!session.csrf_token) throw new ApiError(tr('chat:pleaseSignInAgain'),401)
    if (sending) throw new ApiError(tr('chat:analysisIsInProgressManageResourcesWhenItFinishes'),409)
    const {controller,current}=begin()
    try {
      const result=await mutateCloudResource(kind,id,action,serverGeneration.current,session.csrf_token,title,controller.signal)
      if (current!==generation.current) throw new ApiError(tr('chat:thisResourceRequestIsNoLongerValid'),409)
      const next=result.workspace_status
      serverGeneration.current=next.generation
      if (next.conversation_id!==status?.conversation_id) clearConversation()
      setStatus(next)
      if (action==='rename') {
        if (kind==='history') setRecent(items=>items.map(item=>item.conversation_id===id ? {...item,title} : item))
        else setReports(items=>items.map(item=>item.report_id===id ? {...item,display_title:title} : item))
        // The successful server acknowledgement already authorizes the title.
        // The open manager refreshes its own page; unrelated facts/resources
        // do not need another transcript and two full projections.
        return
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
          if (current!==generation.current) throw new ApiError(tr('chat:thisResourceRequestIsNoLongerValid'),409)
          setMessages(page.items.flatMap(historyItemToMessages))
        }
        await loadResources(controller,current)
      }
      void synchronize().catch(caught => {
        if (current===generation.current) failure(caught,'resource_mutation')
      })
    } catch (caught) { if (current===generation.current) failure(caught,'resource_mutation'); throw caught }
  }

  const bulk=async (kind: 'history' | 'reports',ids: string[],action: CloudResourceAction): Promise<BatchOperationResult> => {
    const result: BatchOperationResult={succeededIds:[],failed:[]}
    for (const id of ids) {
      try { await mutate(kind,id,action); result.succeededIds.push(id) }
      catch (caught) {
        result.failed.push({id,reason:tr('chat:theOperationWasNotCompletedReloadTheResources')})
        if (caught instanceof ApiError && [401,403,409].includes(caught.status)) {
          for (const remaining of ids.slice(result.succeededIds.length+result.failed.length)) {
            result.failed.push({id:remaining,reason:tr('chat:resourceAuthorizationHasExpiredReloadTheResources')})
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
        ? tr('chat:cannotVerifyReportTemplatesRefreshTheModelAndTry') : null)
      setTemplates(nextTemplates.items.map(item => ({key:item.template_key,label:item.display_name,
        description:item.description,compatible:item.selectable,selectable:item.selectable,
        compatibilityStatus:item.compatibility_status})))
    } catch (caught) {
      if (current !== generation.current) return
      if (caught instanceof ApiError && caught.status === 401) throw caught
      setTemplates([]); setTemplate(null)
      setTemplateError(caught instanceof ApiError && caught.failure ? publicFailureMessage(caught.failure)
        : tr('chat:cannotVerifyReportTemplatesRefreshTheModelAndTry'))
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
      productMode.current = models.value.product_mode === true
      setStatus(nextStatus)
      serverGeneration.current = nextStatus.generation
      if (models.value.product_mode) {
        const workspaces = await readCloudWorkspaces('', undefined, controller.signal)
        if (current !== generation.current) return
        setNoWorkspaceAccess(workspaces.items.length === 0 && !workspaces.partial)
      }
      if (nextStatus.execution_ready || models.value.persistence_enabled) {
        void loadResources(controller,current).catch(caught=>{
          if(current===generation.current)failure(caught,'history')
        })

      }
      if (nextStatus.selected_model_key && models.value.items.some(item => item.key === nextStatus.selected_model_key)) {
        setTemplatesLoading(true)
        await loadTemplates(controller, current)
      }
    } catch (caught) {
      if (current !== generation.current) return
      failure(caught, 'catalog')
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
    setLoading(true); setError(null); setReloadModels(false); setTemplateError(null)
    await load()
  }

  const choose = async (option: CatalogOption, resourceUrl?: string) => {
    if (!session.csrf_token || !catalog || (!catalog.product_mode && !catalog.items.some(item => item.key === option.key))) return false
    const { controller, current } = begin()
    clearConversation()
    setError(null); setTemplate(null); setTemplates([]); setTemplateError(null); setModelSelectionLoading(true); setReloadModels(false)
    try {
      let nextStatus: CloudWorkspaceStatus
      try {
        nextStatus = resourceUrl
          ? await openCloudResourceLink(resourceUrl,session.csrf_token,serverGeneration.current,controller.signal)
          : await selectCloudModel(option.key, session.csrf_token, serverGeneration.current, controller.signal)
      } catch (caught) {
        if (!(caught instanceof ApiError) || caught.status !== 409 || current !== generation.current) throw caught
        const latest = await readCloudStatus(controller.signal)
        if (current !== generation.current) return false
        nextStatus = resourceUrl
          ? await openCloudResourceLink(resourceUrl,session.csrf_token,latest.generation,controller.signal)
          : await selectCloudModel(option.key, session.csrf_token, latest.generation, controller.signal)
      }
      if (current !== generation.current) return false
      if (catalog.product_mode) {
        const boundCatalog = await readCloudCatalog(controller.signal)
        if (current !== generation.current) return false
        if (!boundCatalog.items.some(item=>item.key===nextStatus.selected_model_key)) throw new Error('Selection mismatch')
        setCatalog(boundCatalog)
      } else if (nextStatus.selected_model_key !== option.key) throw new Error('Selection mismatch')
      setStatus(nextStatus)
      serverGeneration.current = nextStatus.generation
      if (nextStatus.report_templates) {
        setTemplates(nextStatus.report_templates.items.map(item=>({key:item.template_key,label:item.display_name,
          description:item.description,compatible:item.selectable,selectable:item.selectable,compatibilityStatus:item.compatibility_status})))
      } else await loadTemplates(controller, current)
      return current === generation.current
    } catch (caught) {
      if (current !== generation.current) return false
      failure(caught, 'selection', option.key)
      return false
    } finally {
      if (current === generation.current) { setTemplatesLoading(false); setModelSelectionLoading(false) }
    }
  }

  const changeConversation=async (id?: string) => {
    if (!status || (!id && !status.execution_ready) || !session.csrf_token) return
    const {controller,current}=begin()
    clearConversation(); setError(null); setTemplates([]); setTemplate(null); setTemplatesLoading(true); setConversationRestoreLoading(Boolean(id))
    try {
      const next=id ? await restoreCloudChat(id,serverGeneration.current,session.csrf_token,controller.signal)
        : await newCloudChat(serverGeneration.current,session.csrf_token,controller.signal)
      if (current!==generation.current) return
      serverGeneration.current=next.generation; setStatus(next)
      if (catalog?.product_mode) {
        const boundCatalog=await readCloudCatalog(controller.signal)
        if (current!==generation.current) return
        setCatalog(boundCatalog)
      }
      if (id) {
        const page=await readCloudConversation(id,controller.signal)
        if (current!==generation.current) return
        if (page.conversation_id!==id) throw new Error('History mismatch')
        setMessages(page.items.flatMap(historyItemToMessages)); setRestored(true)
      }
      await loadTemplates(controller,current)
    } catch (caught) {
      if (current!==generation.current) return
      failure(caught,'history')
    } finally { if (current===generation.current) { setTemplatesLoading(false); setConversationRestoreLoading(false) } }
  }

  const send=async (content: string) => {
    if (!status?.execution_ready || !status.conversation_id || !session.csrf_token || sending) return
    const conversation=status.conversation_id
    const {controller,current}=begin()
    const requestId=crypto.randomUUID()
    setSending(true); setError(null); setReloadModels(false)
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
      failure(caught,'chat',status.selected_model_key || undefined)
    } finally { if (current===generation.current) setSending(false) }
  }

  const options: CatalogOption[] = (catalog?.items || []).map(item => ({key:item.key,
    label:item.display_name, description:item.workspace_display_name, compatible:true, selectable:true}))
  const selected = options.find(item => item.key === status?.selected_model_key) || null
  const notice = loading ? tr('chat:loadingAccessibleCloudModels')
    : error || sessionCheckError || (catalog?.product_mode && !selected
      ? noWorkspaceAccess ? tr('composer:noWorkspaceAccess') : tr('chat:selectADataModel')
      : catalog?.product_mode && selected ? tr('chat:anAccessibleDataModelIsSelected')
      : catalog?.status === 'partial' ?
      (catalog.authorization_scope_complete === false && (catalog.unverified_count || 0) > 0
        ? tr('chat:partialCatalogUnverified', {count:catalog.unverified_count})
        : tr('chat:accessibleModelsAreShownSomeModelsMayNotBe'))
      : catalog?.status === 'forbidden' ? tr('chat:youAreSignedInButThisAccountCannotRead')
      : catalog?.status === 'error' ? tr('chat:theDataModelCatalogIsUnavailableRefreshAndTry')
      : selected && !status?.execution_ready ? cloudDenialMessage('cloud_execution_blocked')
      : selected ? tr('chat:anAccessibleDataModelIsSelected')
      : !options.length ? tr('chat:noAccessibleDataModelsWereFound') : tr('chat:selectADataModelToBegin'))
  const executionBlocked = !status?.execution_ready ? tr('chat:dataAnalysisIsUnavailableTryAgainLater') : null

  const retryResources=(kind: 'history'|'report') => {
    const controller=new AbortController()
    void loadResources(controller,generation.current,kind).catch(caught=>failure(caught,kind))
  }
  const content=<>
    <ConversationView projectionContext={{mode:"real",cloud:true,csrf:session.csrf_token || "",generation:status?.generation,conversationId:status?.conversation_id,onAuthInvalid}} messages={messages} sending={sending} loadingConversation={conversationRestoreLoading} restored={restored}
      welcomeDescription={tr('chat:selectACloudModelAccessibleToThisAccount')} />
    <Composer key={status?.conversation_id || 'cloud-unselected'} sending={sending} semanticModel={selected} semanticModelOptions={options}
      cloudModelPicker={catalog?.product_mode ? close=><CloudCatalogPicker onSelect={choose} onClose={close} onFailure={catalogFailure}
        onOpenLink={url=>choose({key:'resource-link',label:'',description:'',compatible:true,selectable:true},url)}/> : undefined}
      statusNotice={<div className="cloud-catalog-status">
        <p className="local-catalog-note" role="status">{publicText(notice)}</p>
        {reloadModels || catalog?.status === 'error' || catalog?.status === 'forbidden'
          ? <button type="button" onClick={() => void refresh()}>{tr('chat:reloadDataModels')}</button> : null}
      </div>}
      loadingSemanticModels={loading} semanticModelError={noWorkspaceAccess ? tr('composer:noWorkspaceAccess') : null}
      semanticModelCompatibilityNotice={modelSelectionLoading ? tr('chat:verifyingModelAccessAndReportTemplates')
        : selected ? executionBlocked : tr('chat:selectADataModel')}
      reportTemplate={template} reportTemplateOptions={templates} loadingReportTemplates={templatesLoading || modelSelectionLoading}
      reportTemplateError={publicText(templateError)} llmProfile={profile} llmProfileOptions={profiles}
      loadingLLMProfiles={loading} llmProfileError={null}
      onSemanticModelChange={option => void choose(option)} onRefreshSemanticModels={refresh}
      onReportTemplateChange={setTemplate} onLLMProfileChange={setProfile}
      onSend={send}
      dataSourceKind="cloud" executionBlockedReason={executionBlocked} />
  </>
  if (!account) return content
  return <div className="app-shell">
    <Sidebar key={status?.execution_ready ? 'ready' : 'blocked'} account={account} collapsed={collapsed} onToggle={onToggle} runtimeMode="real"
      resourceLoaders={status?.execution_ready || catalog?.persistence_enabled ? resourceLoaders : undefined}
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
    <main className="chat-main">{content}
      {historyError ? <p className="local-catalog-note" role="status">{historyError} <button disabled={historyLoading} onClick={()=>retryResources('history')}>{tr('chat:retrySidebarResources')}</button></p> : null}
      {reportError ? <p className="local-catalog-note" role="status">{reportError} <button disabled={reportsLoading} onClick={()=>retryResources('report')}>{tr('chat:retrySidebarResources')}</button></p> : null}
    </main>
  </div>
}
