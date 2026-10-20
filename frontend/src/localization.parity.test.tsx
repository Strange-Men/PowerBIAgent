import { act,fireEvent,render,screen,waitFor } from '@testing-library/react'
import { afterEach,expect,it,vi } from 'vitest'
import { App } from './App'
import { useAuth } from './hooks/useAuth'
import { usePowerBIAgent } from './hooks/usePowerBIAgent'
import { i18n,setLocale,tr } from './i18n'
import { publicFailureMessage } from './failure'
import type { PublicFailureCode } from './types'

vi.mock('./hooks/useAuth',()=>({useAuth:vi.fn()}))
vi.mock('./hooks/usePowerBIAgent',()=>({usePowerBIAgent:vi.fn()}))
afterEach(async()=>{await setLocale('zh-CN');vi.clearAllMocks()})

it.each(['zh-CN','en-US'] as const)('login, expiry, loading and account errors in %s',async locale=>{
  await setLocale(locale)
  const login=vi.fn(),refresh=vi.fn(),logout=vi.fn()
  const auth={session:null,state:'SESSION_EXPIRED',login,refresh,logout,generation:7,
    logoutPending:false,sessionCheckError:null}
  vi.mocked(useAuth).mockReturnValue(auth as never)
  const view=render(<App />)
  expect(screen.getByText(tr('auth:yourSessionHasExpiredSignInAgain'))).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:tr('sidebar:signInWithMicrosoft')}))
  expect(login).toHaveBeenCalledOnce()
  expect(usePowerBIAgent).not.toHaveBeenCalled()
  expect(screen.queryByRole('combobox',{name:tr('common:language')})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:tr('resources:settings')}))
  expect(screen.getByRole('button',{name:tr('resources:general')})).toHaveClass('is-active')
  await act(async()=>{fireEvent.change(screen.getByRole('combobox',{name:tr('common:language')}),
    {target:{value:locale==='zh-CN'?'en-US':'zh-CN'}})})
  expect(refresh).not.toHaveBeenCalled()
  expect(logout).not.toHaveBeenCalled()
  expect(screen.getByText(tr('auth:yourSessionHasExpiredSignInAgain'))).toBeVisible()
  vi.mocked(useAuth).mockReturnValue({...auth,state:'SESSION_ESTABLISHING'} as never)
  view.rerender(<App />)
  expect(screen.getByRole('status')).toHaveTextContent(tr('auth:checkingYourSession'))
})

it.each(['zh-CN','en-US'] as const)('Local workspace model/template/composer retain bindings in %s',async locale=>{
  await setLocale(locale)
  const model={key:'model-1',label:'Synthetic Sales',description:'Connected',compatible:true,selectable:true}
  const template={key:'sales_report',label:'简易销售分析模板',description:'基于销售指标快速生成 KPI、趋势与分类分析',compatible:true,selectable:true}
  const profile={profile_key:'deepseek',display_name:'DeepSeek',model:'deepseek-chat',available:true,default:true,provider_protocol:'openai_chat_completions'}
  const send=vi.fn().mockResolvedValue(undefined),selectModel=vi.fn(),selectTemplate=vi.fn(),selectLLM=vi.fn(),newChat=vi.fn()
  const idle=vi.fn().mockResolvedValue(undefined)
  vi.mocked(useAuth).mockReturnValue({session:{identity_mode:'LOCAL_DEV'},state:'LOCAL_DEV'} as never)
  vi.mocked(usePowerBIAgent).mockReturnValue({messages:[],sending:false,loadingConversation:false,hasRestoredHistory:false,
    activeConversationId:'same-conversation',effectiveRuntimeMode:'real',recentConversations:[],recentReports:[],sidebarError:null,
    selectedSemanticModel:model,semanticModelOptions:[model],selectedReportTemplate:null,reportTemplateOptions:[template],
    selectedLLMProfile:profile,llmProfileOptions:[profile],loadingSemanticModels:false,loadingReportTemplates:false,loadingLLMProfiles:false,
    semanticModelError:null,semanticModelCompatibilityNotice:null,reportTemplateError:null,llmProfileError:null,
    submitMessage:send,setSelectedSemanticModel:selectModel,setSelectedReportTemplate:selectTemplate,setSelectedLLMProfile:selectLLM,
    refreshSemanticModels:idle,startNewChat:newChat,search:idle,rename:idle,archive:idle,restore:idle,remove:idle,
    removeReport:idle,archiveReport:idle,renameReport:idle,bulkRemoveConversations:idle,bulkArchiveConversations:idle,
    bulkRestoreConversations:idle,bulkRemoveReports:idle,bulkArchiveReports:idle,bulkRestoreReports:idle} as never)
  render(<App />)
  fireEvent.click(screen.getByRole('button',{name:tr('composer:openDataAndReportOptions')}))
  fireEvent.click(screen.getByRole('button',{name:/Synthetic Sales/}))
  expect(selectModel).toHaveBeenCalledWith(model)
  fireEvent.click(screen.getByRole('button',{name:tr('composer:openDataAndReportOptions')}))
  fireEvent.click(screen.getByRole('button',{name:new RegExp(tr('reports:simpleTemplate'))}))
  expect(selectTemplate).toHaveBeenCalledWith(template)
  const input=screen.getByRole('textbox',{name:tr('composer:askAboutYourPowerBiData')})
  fireEvent.change(input,{target:{value:'用户原始输入 / original input'}})
  fireEvent.click(screen.getByRole('button',{name:tr('composer:send')}))
  await waitFor(()=>expect(send).toHaveBeenCalledWith('用户原始输入 / original input'))
  await act(async()=>{await setLocale(locale==='zh-CN'?'en-US':'zh-CN')})
  expect(newChat).not.toHaveBeenCalled()
  expect(send).toHaveBeenCalledOnce()
  expect(selectModel).toHaveBeenCalledOnce()
  expect(selectTemplate).toHaveBeenCalledOnce()
  expect(selectLLM).not.toHaveBeenCalled()
  expect(screen.getByRole('textbox',{name:tr('composer:askAboutYourPowerBiData')})).toBeVisible()
})

it.each(['zh-CN','en-US'] as const)('public failures remain one language in %s',async locale=>{
  await setLocale(locale)
  const codes:PublicFailureCode[]=['AUTH_REQUIRED','AUTH_EXPIRED','AUTH_CONSENT_REQUIRED','AUTH_FORBIDDEN',
    'RESOURCE_NOT_ACCESSIBLE','MODEL_RESOLUTION_FAILED','SCHEMA_UNAVAILABLE','QUERY_REJECTED','QUERY_TIMEOUT',
    'RATE_LIMITED','UPSTREAM_UNAVAILABLE','CONTRACT_DRIFT','REPORT_TEMPLATE_INCOMPATIBLE','REPORT_TEMPLATE_UNAVAILABLE',
    'REPORT_DATA_UNAVAILABLE','REPORT_EXECUTION_FAILED','REPORT_RENDER_FAILED','POWERBI_CONNECTION_LOST',
    'SEMANTIC_MODEL_STALE','LLM_SERVICE_UNAVAILABLE','REQUEST_TIMEOUT','VALIDATION_FAILED','INTERNAL_FAILURE']
  for(const code of codes){
    const text=publicFailureMessage({code,stage:'internal',retryable:false,recovery_action:'none'})
    expect(text).not.toContain(':')
    expect(/[\u4e00-\u9fff]/.test(text)).toBe(locale==='zh-CN')
  }
  expect(i18n.language).toBe(locale)
})
