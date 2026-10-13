import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CloudWorkspace } from './CloudWorkspace'
import * as api from '../api/client'
import type { CloudWorkspaceStatus } from '../cloudTypes'

vi.mock('../api/client', async importOriginal => ({
  ...await importOriginal<typeof import('../api/client')>(),
  readCloudCatalog: vi.fn(), readCloudStatus: vi.fn(), selectCloudModel: vi.fn(),
  readCloudProfiles: vi.fn(), readCloudTemplates: vi.fn(),
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
})

describe('Cloud control-plane UX', () => {
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
