import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CloudAccountSettings } from './CloudAccountSettings'
import * as api from '../api/client'

vi.mock('../api/client', async importOriginal => ({...await importOriginal<typeof import('../api/client')>(),readCloudCatalog:vi.fn(),readCloudStatus:vi.fn()}))
const account = {session:{identity_mode:'ENTRA_BFF' as const,authenticated:true,
  display_name:'当前合成账号',preferred_username:null,state:'SIGNED_IN' as const,
  csrf_token:'private-synthetic-csrf',expires_in:3600},state:'SIGNED_IN' as const,
  login:vi.fn(),logout:vi.fn().mockResolvedValue(undefined)}

describe('Cloud account settings', () => {
  it('requests identity recovery on expired catalog without fetching status',async()=>{
    const refresh=vi.fn()
    vi.mocked(api.readCloudCatalog).mockRejectedValueOnce(new api.ApiError('PRIVATE_EXPIRED',401))
    const previous=vi.mocked(api.readCloudStatus).mock.calls.length
    render(<CloudAccountSettings account={{...account,refresh}} />)
    fireEvent.click(screen.getByRole('button',{name:'数据与模型'}))
    await screen.findByRole('alert')
    expect(refresh).toHaveBeenCalledOnce()
    expect(api.readCloudStatus).toHaveBeenCalledTimes(previous)
    expect(screen.queryByText('PRIVATE_EXPIRED')).not.toBeInTheDocument()
  })
  it('shows real account fields without technical identity or token controls', () => {
    render(<CloudAccountSettings account={account} />)
    expect(screen.getByText('当前合成账号')).toBeInTheDocument()
    expect(screen.queryByText(/private-synthetic-csrf/)).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'退出'}))
    expect(account.logout).toHaveBeenCalledOnce()
  })

  it('shows scoped partial models and safe names rather than internal keys', async () => {
    vi.mocked(api.readCloudCatalog).mockResolvedValue({status:'partial',items:[{
      key:'opaque-private-key',display_name:'合成云模型',workspace_display_name:'合成工作区',
    }]} as never)
    vi.mocked(api.readCloudStatus).mockResolvedValue({selected_model_key:'opaque-private-key',execution_ready:false} as never)
    render(<CloudAccountSettings account={account} />)
    fireEvent.click(screen.getByRole('button',{name:'数据与模型'}))
    expect(await screen.findByText('合成云模型')).toBeInTheDocument()
    expect(screen.getByText(/部分模型/)).toBeInTheDocument()
    expect(screen.queryByText(/opaque-private-key/)).not.toBeInTheDocument()
  })
})
