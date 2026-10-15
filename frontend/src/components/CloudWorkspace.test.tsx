import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CloudWorkspace } from './CloudWorkspace'
import * as api from '../api/client'
import type { CloudWorkspaceStatus } from '../cloudTypes'

vi.mock('../api/client', async importOriginal => ({
  ...await importOriginal<typeof import('../api/client')>(),
  readCloudCatalog: vi.fn(), readCloudStatus: vi.fn(), selectCloudModel: vi.fn(),
  readCloudProfiles: vi.fn(), readCloudTemplates: vi.fn(),
  sendCloudChat:vi.fn(),readCloudHistory:vi.fn(),readCloudReports:vi.fn(),readCloudConversation:vi.fn(),
  newCloudChat:vi.fn(),restoreCloudChat:vi.fn(),
  listCloudConversations:vi.fn(),listCloudReports:vi.fn(),mutateCloudResource:vi.fn(),
}))
const status: CloudWorkspaceStatus = {selected_model_key:null,conversation_id:null,generation:0,
  execution_ready:false,blockers:['numeric_contract','query_completeness']}
const session = {identity_mode:'ENTRA_BFF' as const, authenticated:true, display_name:'Synthetic A',
  preferred_username:null, state:'SIGNED_IN' as const, csrf_token:'synthetic-proof',expires_in:3600}
const models = [{key:'opaque-a',display_name:'模型甲',workspace_display_name:'合成工作区',source:'fabric_iq',accessibility:'available'},
  {key:'opaque-b',display_name:'模型乙',workspace_display_name:'合成工作区',source:'fabric_iq',accessibility:'available'}]

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.readCloudCatalog).mockResolvedValue({status:'partial',runtime_mode:'real',items:models,
    workspace_scope_complete:true,individual_share_coverage:'configured_seeds_only',inaccessible_count:0,error_type:null} as never)
  vi.mocked(api.readCloudStatus).mockResolvedValue(status)
  vi.mocked(api.readCloudProfiles).mockResolvedValue({items:[]} as never)
  vi.mocked(api.readCloudTemplates).mockResolvedValue({items:[],reason_code:'no_eligible_report_template'} as never)
  vi.mocked(api.readCloudHistory).mockResolvedValue({items:[]} as never)
  vi.mocked(api.readCloudReports).mockResolvedValue({items:[]} as never)
})

describe('Synthetic Cloud product wiring',()=>{
  const ready={...status,selected_model_key:'opaque-a',conversation_id:'synthetic-current',generation:1,execution_ready:true,blockers:[]}
  const account={session,state:'SIGNED_IN' as const,login:vi.fn(),logout:vi.fn().mockResolvedValue(undefined)}
  const summary={conversation_id:'synthetic-old',title:'合成历史',source_mode:'mock'}
  const enable=()=>{
    vi.mocked(api.readCloudStatus).mockResolvedValue(ready)
    vi.mocked(api.readCloudProfiles).mockResolvedValue({items:[{profile_key:'deepseek',display_name:'合成 AI',available:true,default:true}]} as never)
  }
  const submit=async()=>{
    const input=await screen.findByRole('textbox',{name:'询问你的 Power BI 数据'})
    fireEvent.change(input,{target:{value:'合成销售问题'}})
    fireEvent.click(screen.getByRole('button',{name:'发送'}))
  }
  it('Cloud rename does not reread unrelated transcript and both resource projections',async()=>{
    enable()
    vi.mocked(api.listCloudConversations).mockResolvedValue({items:[summary],next_cursor:null,total_count:1} as never)
    vi.mocked(api.listCloudReports).mockResolvedValue({items:[],next_cursor:null,total_count:0} as never)
    vi.mocked(api.mutateCloudResource).mockResolvedValue({workspace_status:ready})
    const prompt=vi.spyOn(window,'prompt').mockReturnValue('已验证新标题')
    try {
      render(<CloudWorkspace session={session} account={account} onAuthInvalid={vi.fn()} />)
      await screen.findByText('模型甲')
      const historyReads=vi.mocked(api.readCloudHistory).mock.calls.length
      const reportReads=vi.mocked(api.readCloudReports).mock.calls.length
      fireEvent.click(screen.getByRole('button',{name:'Synthetic A'}))
      fireEvent.click(screen.getByRole('menuitem',{name:'设置'}))
      fireEvent.click(screen.getByRole('button',{name:'对话管理'}))
      fireEvent.click(await screen.findByRole('button',{name:'重命名'}))
      await waitFor(()=>expect(api.mutateCloudResource).toHaveBeenCalledWith(
        'history','synthetic-old','rename',1,'synthetic-proof','已验证新标题',expect.any(AbortSignal)))
      await waitFor(()=>expect(api.listCloudConversations).toHaveBeenCalledTimes(2))
      expect(api.readCloudHistory).toHaveBeenCalledTimes(historyReads)
      expect(api.readCloudReports).toHaveBeenCalledTimes(reportReads)
      expect(api.readCloudConversation).not.toHaveBeenCalled()
    } finally { prompt.mockRestore() }
  })
  it.each([['execution',403],['conflict',409],['network',0],['upstream',503]] as const)(
    'preserves verified catalog and selection on %s chat failure',async(kind,httpStatus)=>{
      enable()
      const invalid=vi.fn()
      vi.mocked(api.sendCloudChat).mockRejectedValue(new api.ApiError('private',httpStatus,undefined,
        kind==='execution' ? {code:'AUTH_FORBIDDEN',stage:'auth',retryable:false,recovery_action:'none'} as never : undefined,
        undefined,kind==='execution' ? 'cloud_execution_blocked' : undefined))
      render(<CloudWorkspace session={session} onAuthInvalid={invalid} />)
      await screen.findByText('模型甲'); await submit()
      await waitFor(()=>expect(api.sendCloudChat).toHaveBeenCalledOnce())
      fireEvent.change(screen.getByRole('textbox',{name:'询问你的 Power BI 数据'}),{target:{value:'重试问题'}})
      await waitFor(()=>expect(screen.getByRole('button',{name:'发送'})).toBeEnabled())
      expect(screen.getByText('模型甲')).toBeInTheDocument()
      expect(invalid).not.toHaveBeenCalled()
      if (kind==='conflict') expect(api.readCloudStatus).toHaveBeenCalledTimes(2)
      fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
      expect(screen.getByRole('button',{name:/模型乙/})).toBeInTheDocument()
    })
  it('resource refusal preserves the valid account and other workspace options',async()=>{
    enable()
    const invalid=vi.fn()
    vi.mocked(api.selectCloudModel).mockRejectedValue(new api.ApiError('private',403,undefined,
      {code:'RESOURCE_NOT_ACCESSIBLE',stage:'tool_execution',retryable:false,recovery_action:'select_model'} as never))
    render(<CloudWorkspace session={session} onAuthInvalid={invalid} />)
    await screen.findByText('模型甲')
    fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
    fireEvent.click(screen.getByRole('button',{name:/模型乙/}))
    await screen.findByText('当前账号无法访问这个数据模型，请切换账号或联系管理员。')
    expect(invalid).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
    expect(screen.queryByRole('button',{name:/模型乙/})).not.toBeInTheDocument()
    expect(screen.getByRole('button',{name:/模型甲/})).toBeInTheDocument()
  })
  it('acknowledges a committed report deletion while the follow-up list is delayed',async()=>{
    enable()
    const report={report_id:'synthetic-report',display_title:'合成报表',conversation_id:ready.conversation_id}
    vi.mocked(api.listCloudConversations).mockResolvedValue({items:[],next_cursor:null,total_count:0} as never)
    vi.mocked(api.listCloudReports).mockImplementation(async resourceStatus=>({
      items:resourceStatus==='active'?[report]:[],next_cursor:null,total_count:resourceStatus==='active'?1:0} as never))
    vi.mocked(api.mutateCloudResource).mockResolvedValue({workspace_status:ready})
    render(<CloudWorkspace session={session} account={account} onAuthInvalid={vi.fn()} />)
    await screen.findByText('模型甲')
    fireEvent.click(screen.getByRole('button',{name:'Synthetic A'}))
    fireEvent.click(screen.getByRole('menuitem',{name:'设置'}))
    fireEvent.click(screen.getByRole('button',{name:'报表管理'}))
    fireEvent.click(await screen.findByRole('checkbox',{name:'选择报表：合成报表'}))
    let finish!: (page: never)=>void
    vi.mocked(api.readCloudReports).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
    vi.spyOn(window,'confirm').mockReturnValue(true)
    fireEvent.click(screen.getByRole('button',{name:'批量删除'}))
    await waitFor(()=>expect(api.mutateCloudResource).toHaveBeenCalled())
    await waitFor(()=>expect(screen.queryByRole('checkbox',{name:'选择报表：合成报表'})).not.toBeInTheDocument())
    expect(screen.getByText('已完成 1 项操作。')).toBeInTheDocument()
    await act(async()=>finish({items:[]} as never))
  })
  it('discards Settings pages after a newer permission refusal',async()=>{
    enable()
    const invalid=vi.fn()
    let resolveOld!: (page: never)=>void
    vi.mocked(api.listCloudConversations).mockImplementationOnce(()=>new Promise(resolve=>{resolveOld=resolve}))
      .mockResolvedValue({items:[],next_cursor:null,total_count:0} as never)
    vi.mocked(api.listCloudReports).mockResolvedValue({items:[],next_cursor:null,total_count:0} as never)
    render(<CloudWorkspace session={session} account={account} onAuthInvalid={invalid} />)
    await screen.findByText('模型甲')
    fireEvent.click(screen.getByRole('button',{name:'Synthetic A'}))
    fireEvent.click(screen.getByRole('menuitem',{name:'设置'}))
    fireEvent.click(await screen.findByRole('button',{name:'对话管理'}))
    await waitFor(()=>expect(api.listCloudConversations).toHaveBeenCalled())
    vi.mocked(api.readCloudCatalog).mockRejectedValueOnce(new api.ApiError('refused',403))
    fireEvent.click(screen.getByRole('button',{name:'关闭设置'}))
    fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
    fireEvent.click(await screen.findByRole('button',{name:'刷新数据模型'}))
    await screen.findByText('暂时无法加载数据模型，请重试。')
    expect(screen.getByRole('button',{name:'搜索聊天'})).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'Synthetic A'})).toBeInTheDocument()
    expect(screen.getByText('模型甲',{selector:'.composer-selection span'})).toBeInTheDocument()
    expect(invalid).not.toHaveBeenCalled()
    await act(async()=>resolveOld({items:[{...summary,title:'旧Principal私有历史'}],next_cursor:null,total_count:1} as never))
    expect(screen.queryByText('旧Principal私有历史')).not.toBeInTheDocument()
  })
  it('sends only generation and bounded request fields, displays protected report links',async()=>{
    enable()
    vi.mocked(api.sendCloudChat).mockImplementation(async body=>({request_id:body.request_id,conversation_id:ready.conversation_id,
      terminal_state:'completed',response_type:'answer',answer:'合成验证回答',report:{report_id:'synthetic-report',
        view_reference:'/api/v1/cloud/reports/synthetic-report',download_reference:'/api/v1/cloud/reports/synthetic-report/download'}} as never))
    render(<CloudWorkspace session={session} onAuthInvalid={vi.fn()} />)
    await screen.findByText('模型甲')
    await submit()
    expect(await screen.findByText('合成验证回答')).toBeInTheDocument()
    const body=vi.mocked(api.sendCloudChat).mock.calls[0][0]
    expect(body).toMatchObject({message:'合成销售问题',expected_generation:1,llm_profile_key:'deepseek'})
    expect(body).not.toHaveProperty('model_key'); expect(body).not.toHaveProperty('conversation_id')
    expect(screen.getByRole('link',{name:/查看/})).toHaveAttribute('href','/api/v1/cloud/reports/synthetic-report')
  })
  it('restores only server-authorized history and starts fresh conversation with retained model',async()=>{
    enable()
    vi.mocked(api.readCloudHistory).mockResolvedValue({items:[summary]} as never)
    vi.mocked(api.restoreCloudChat).mockResolvedValue({...ready,conversation_id:'synthetic-old',generation:2})
    vi.mocked(api.readCloudConversation).mockResolvedValue({conversation_id:'synthetic-old',items:[{
      request_id:'old-answer',user_message:'旧合成问题',answer:'旧合成回答',terminal_state:'completed',response_type:'answer'}]} as never)
    vi.mocked(api.newCloudChat).mockResolvedValue({...ready,conversation_id:'synthetic-new',generation:3})
    render(<CloudWorkspace session={session} onAuthInvalid={vi.fn()} account={account} />)
    fireEvent.click(await screen.findByRole('button',{name:'合成历史'}))
    expect(await screen.findByText('旧合成回答')).toBeInTheDocument()
    expect(api.restoreCloudChat).toHaveBeenCalledWith('synthetic-old',1,'synthetic-proof',expect.any(AbortSignal))
    fireEvent.click(screen.getByRole('button',{name:'新聊天'}))
    await waitFor(()=>expect(api.newCloudChat).toHaveBeenCalledWith(2,'synthetic-proof',expect.any(AbortSignal)))
    await waitFor(()=>expect(screen.queryByText('旧合成回答')).not.toBeInTheDocument())
    expect(screen.getByText('模型甲')).toBeInTheDocument()
  })
  it('discards delayed chat after model switch even if fetch ignores abort',async()=>{
    enable()
    let finish!: (value: never)=>void
    vi.mocked(api.sendCloudChat).mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
    vi.mocked(api.selectCloudModel).mockResolvedValue({...ready,selected_model_key:'opaque-b',conversation_id:'synthetic-b',generation:2})
    render(<CloudWorkspace session={session} onAuthInvalid={vi.fn()} />)
    await screen.findByText('模型甲'); await submit()
    await waitFor(()=>expect(api.sendCloudChat).toHaveBeenCalled())
    const body=vi.mocked(api.sendCloudChat).mock.calls[0][0]
    fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
    fireEvent.click(screen.getByRole('button',{name:/模型乙/}))
    await screen.findByText('模型乙')
    await act(async()=>finish({request_id:body.request_id,conversation_id:ready.conversation_id,answer:'迟到私有回答',terminal_state:'completed'} as never))
    expect(screen.queryByText('迟到私有回答')).not.toBeInTheDocument()
    expect(vi.mocked(api.sendCloudChat).mock.calls[0][2]?.aborted).toBe(true)
  })
  it('clears displayed business data on revoked or expired chat identity',async()=>{
    enable()
    const invalid=vi.fn()
    vi.mocked(api.sendCloudChat).mockRejectedValue(new api.ApiError('PRIVATE_AUTH_DETAIL',401))
    render(<CloudWorkspace session={session} onAuthInvalid={invalid} />)
    await screen.findByText('模型甲'); await submit()
    await waitFor(()=>expect(invalid).toHaveBeenCalledOnce())
    expect(screen.queryByText('合成销售问题')).not.toBeInTheDocument()
    expect(screen.queryByText('PRIVATE_AUTH_DETAIL')).not.toBeInTheDocument()
  })
})

describe('Cloud control-plane UX', () => {
  it.each([
    ['test_scope_missing',503,'已登录；测试资源白名单尚未配置，请联系管理员配置已批准的测试资源。'],
    ['cloud_execution_blocked',403,'已登录；云端业务验收尚未完成，数据问答与报表暂未开放。'],
  ] as const)('renders %s once while retaining the signed-in account',async(reason,httpStatus,message)=>{
    const invalid=vi.fn()
    const account={session,state:'SIGNED_IN' as const,login:vi.fn(),logout:vi.fn().mockResolvedValue(undefined)}
    vi.mocked(api.readCloudCatalog).mockRejectedValueOnce(new api.ApiError('private',httpStatus,undefined,undefined,undefined,reason))
    render(<CloudWorkspace session={session} account={account} onAuthInvalid={invalid} />)
    await screen.findByText(message)
    expect(screen.getAllByText(message)).toHaveLength(1)
    expect(screen.getByRole('button',{name:'Synthetic A'})).toBeInTheDocument()
    expect(invalid).not.toHaveBeenCalled()
    expect(screen.getByRole('button',{name:'发送'})).toBeDisabled()
    fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
    expect(screen.getAllByText(message)).toHaveLength(1)
    expect(screen.getByRole('status').closest('.composer-wrap')).toBeInTheDocument()
  })
  it('clears catalog when concurrent profile loading detects an expired identity', async () => {
    const invalid=vi.fn()
    vi.mocked(api.readCloudProfiles).mockRejectedValue(new api.ApiError('SYNTHETIC_EXPIRED',401))
    render(<CloudWorkspace session={session} onAuthInvalid={invalid} />)
    await waitFor(() => expect(invalid).toHaveBeenCalledOnce())
    expect(api.readCloudStatus).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
    expect(screen.queryByRole('button',{name:/模型甲/})).not.toBeInTheDocument()
    expect(screen.getByRole('button',{name:'发送'})).toBeDisabled()
  })

  it('filters verified model display names locally without claiming catalog emptiness', async () => {
    render(<CloudWorkspace session={session} onAuthInvalid={vi.fn()} />)
    await screen.findByText(/部分模型/)
    fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
    const filter = screen.getByRole('searchbox',{name:'筛选数据模型'})
    fireEvent.change(filter,{target:{value:'模型乙'}})
    expect(screen.queryByRole('button',{name:/模型甲/})).not.toBeInTheDocument()
    expect(screen.getByRole('button',{name:/模型乙/})).toBeInTheDocument()
    fireEvent.change(filter,{target:{value:'不存在的名称'}})
    expect(screen.getByText('没有匹配的模型，请更换筛选词。')).toBeInTheDocument()
    expect(screen.queryByText('当前没有可用数据模型。')).not.toBeInTheDocument()
    expect(api.readCloudCatalog).toHaveBeenCalledTimes(1)
    expect(api.selectCloudModel).not.toHaveBeenCalled()
    expect(screen.getByRole('button',{name:'发送'})).toBeDisabled()
  })

  it.each(['selection', 'reload'])('retains a verified model when template loading fails after %s', async mode => {
    const selected = {...status,selected_model_key:'opaque-a',conversation_id:'verified-a',generation:1}
    vi.mocked(api.selectCloudModel).mockResolvedValue(selected)
    if (mode === 'reload') vi.mocked(api.readCloudStatus).mockResolvedValue(selected)
    vi.mocked(api.readCloudTemplates).mockRejectedValue(new api.ApiError('PRIVATE_TEMPLATE_DETAIL',503,undefined,
      {code:'RATE_LIMITED',stage:'tool_execution',retryable:true,recovery_action:'retry'} as never))
    render(<CloudWorkspace session={session} onAuthInvalid={vi.fn()} />)
    await screen.findByText(/部分模型/)
    if (mode === 'selection') {
      fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
      fireEvent.click(await screen.findByRole('button',{name:/模型甲/}))
    }
    await waitFor(() => expect(api.readCloudTemplates).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText('模型甲')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
    expect(await screen.findByText('云端数据服务请求较多，请稍后重试。')).toBeInTheDocument()
    expect(screen.queryByText('PRIVATE_TEMPLATE_DETAIL')).not.toBeInTheDocument()
    expect(screen.getByRole('button',{name:'发送'})).toBeDisabled()
    expect(screen.getByText('数据问答暂不可用，请稍后重试。')).toBeInTheDocument()
  })

  it('discloses unfinished model authorization without enabling factual execution', async () => {
    vi.mocked(api.readCloudCatalog).mockResolvedValue({status:'partial',items:[models[0]],
      authorization_scope_complete:false,unverified_count:2} as never)
    render(<CloudWorkspace session={session} onAuthInvalid={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('还有 2 个模型尚未验证，请刷新目录后重试。'))
    expect(api.selectCloudModel).not.toHaveBeenCalled()
    expect(screen.getByRole('button',{name:'发送'})).toBeDisabled()
  })

  it('shows the safe Cloud timeout recovery message without exposing diagnostic text', async () => {
    vi.mocked(api.readCloudCatalog).mockRejectedValue(new api.ApiError('PRIVATE_PROVIDER_DETAIL',503,undefined,
      {code:'QUERY_TIMEOUT',stage:'tool_execution',retryable:true,recovery_action:'retry'} as never))
    render(<CloudWorkspace session={session} onAuthInvalid={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('云端数据服务响应超时，请重试。'))
    expect(screen.queryByText('PRIVATE_PROVIDER_DETAIL')).not.toBeInTheDocument()
    expect(screen.getByRole('button',{name:'发送'})).toBeDisabled()
  })

  it('revalidates catalog and reloads templates for a previously explicit selection', async () => {
    vi.mocked(api.readCloudStatus).mockResolvedValue({...status,selected_model_key:'opaque-a',conversation_id:'restored-a'})
    vi.mocked(api.readCloudTemplates).mockResolvedValue({items:[{template_key:'sales_report',display_name:'合成销售模板',
      description:'合成',selectable:true,compatibility_status:'partial'}],reason_code:null} as never)
    render(<CloudWorkspace session={session} onAuthInvalid={vi.fn()} />)
    await waitFor(() => expect(api.readCloudTemplates).toHaveBeenCalled())
    expect(api.selectCloudModel).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
    expect(await screen.findByRole('button',{name:/合成销售模板/})).toBeInTheDocument()
  })

  it('requires explicit selection even for one model and keeps factual execution closed', async () => {
    vi.mocked(api.readCloudCatalog).mockResolvedValue({status:'partial',items:[models[0]]} as never)
    vi.mocked(api.selectCloudModel).mockResolvedValue({...status,selected_model_key:'opaque-a',conversation_id:'new-a'})
    render(<CloudWorkspace session={session} onAuthInvalid={vi.fn()} />)
    await screen.findByText(/部分模型/)
    expect(api.selectCloudModel).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
    expect(screen.queryByText(/仍可正常进行数据问答/)).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button',{name:/模型甲/}))
    await waitFor(() => expect(api.selectCloudModel).toHaveBeenCalledWith('opaque-a','synthetic-proof',0,expect.any(AbortSignal)))
    expect(screen.getByRole('button',{name:'发送'})).toBeDisabled()
    expect(screen.getByText(/数据问答暂不可用/)).toBeInTheDocument()
    expect(screen.queryByText(/Desktop discovery/)).not.toBeInTheDocument()
  })

  it('discards a previous model selection response that arrives late', async () => {
    let resolveOld!: (value: CloudWorkspaceStatus) => void
    vi.mocked(api.selectCloudModel).mockImplementation(key => key === 'opaque-a'
      ? new Promise(resolve => { resolveOld = resolve })
      : Promise.resolve({...status,selected_model_key:'opaque-b',conversation_id:'new-b'}))
    render(<CloudWorkspace session={session} onAuthInvalid={vi.fn()} />)
    await screen.findByText(/部分模型/)
    fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
    fireEvent.click(await screen.findByRole('button',{name:/模型甲/}))
    fireEvent.click(screen.getByRole('button',{name:'打开数据与报表选项'}))
    fireEvent.click(screen.getByRole('button',{name:/模型乙/}))
    await waitFor(() => expect(screen.getByText('模型乙')).toBeInTheDocument())
    await act(async () => resolveOld({...status,selected_model_key:'opaque-a',conversation_id:'old-a'}))
    expect(screen.getByText('模型乙')).toBeInTheDocument()
    expect(screen.queryByText('模型甲')).not.toBeInTheDocument()
  })

  it('aborts requests on identity remount without publishing an old catalog', async () => {
    let resolveOld!: (value: never) => void
    vi.mocked(api.readCloudCatalog).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const first = render(<CloudWorkspace session={session} onAuthInvalid={vi.fn()} />)
    await waitFor(() => expect(api.readCloudCatalog).toHaveBeenCalled())
    const signal = vi.mocked(api.readCloudCatalog).mock.calls[0][0]
    first.unmount()
    expect(signal?.aborted).toBe(true)
    render(<CloudWorkspace session={{...session,display_name:'Synthetic B'}} onAuthInvalid={vi.fn()} />)
    await screen.findByText(/部分模型/)
    await act(async () => resolveOld({status:'ready',items:[{...models[0],display_name:'旧用户私有模型'}]} as never))
    expect(screen.queryByText(/旧用户私有模型/)).not.toBeInTheDocument()
  })
})
