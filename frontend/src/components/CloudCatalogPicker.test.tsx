import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { CloudCatalogPicker } from './CloudCatalogPicker'
import * as api from '../api/client'
import type { CloudCatalogPage } from '../cloudTypes'

vi.mock('../api/client', async original => ({...await original<typeof import('../api/client')>(),
  readCloudWorkspaces:vi.fn(), readCloudResources:vi.fn()}))
const page = (name:string, kind:'Workspace'|'SemanticModel'|'Report', next:string|null=null):CloudCatalogPage => ({
  items:[{key:name,display_name:name,kind}],next_cursor:next,partial:!!next,coverage:'workspace_membership_only'})
beforeEach(()=>{
  vi.resetAllMocks()
  vi.mocked(api.readCloudWorkspaces).mockResolvedValue(page('Workspace A','Workspace'))
  vi.mocked(api.readCloudResources).mockResolvedValue(page('Model A','SemanticModel','next'))
})
it('opens an explicit link without selecting a workspace candidate',async()=>{
  const open=vi.fn().mockResolvedValue(true),close=vi.fn(),select=vi.fn()
  render(<CloudCatalogPicker onSelect={select} onOpenLink={open} onClose={close} onFailure={vi.fn()}/> )
  fireEvent.click(screen.getByRole('button',{name:'通过 Power BI / Fabric 链接打开数据资源'}))
  const url='https://app.powerbi.com/groups/00000000-0000-0000-0000-000000000011/datasets/00000000-0000-0000-0000-000000000010/details'
  fireEvent.change(screen.getByRole('textbox',{name:'Power BI / Fabric 资源链接'}),{target:{value:url}})
  fireEvent.click(screen.getByRole('button',{name:'验证并打开'}))
  await waitFor(()=>expect(open).toHaveBeenCalledWith(url))
  expect(select).not.toHaveBeenCalled()
  expect(close).toHaveBeenCalledOnce()
})
it('lazily enters a workspace, pages metadata and explicitly selects one resource',async()=>{
  const select=vi.fn().mockResolvedValue(true), close=vi.fn()
  render(<CloudCatalogPicker onSelect={select} onClose={close} onFailure={vi.fn()} />)
  expect(api.readCloudResources).not.toHaveBeenCalled()
  fireEvent.click(await screen.findByRole('button',{name:'Workspace A'}))
  fireEvent.click(await screen.findByRole('button',{name:'下一页'}))
  await waitFor(()=>expect(api.readCloudResources).toHaveBeenLastCalledWith('Workspace A','SemanticModel','','next',expect.any(AbortSignal)))
  fireEvent.click(await screen.findByRole('button',{name:'Model A'}))
  await waitFor(()=>expect(select).toHaveBeenCalledWith(expect.objectContaining({key:'Model A'})))
  expect(close).toHaveBeenCalledOnce()
})
it('ignores an old workspace response arriving after the new workspace',async()=>{
  let late!:(page:CloudCatalogPage)=>void
  vi.mocked(api.readCloudWorkspaces).mockResolvedValue({...page('Workspace A','Workspace'),
    items:[...page('Workspace A','Workspace').items,...page('Workspace B','Workspace').items]})
  vi.mocked(api.readCloudResources).mockImplementationOnce(()=>new Promise(resolve=>{late=resolve}))
    .mockResolvedValue(page('Model B','SemanticModel'))
  render(<CloudCatalogPicker onSelect={vi.fn()} onClose={vi.fn()} onFailure={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button',{name:'Workspace A'}))
  await waitFor(()=>expect(api.readCloudResources).toHaveBeenCalledOnce())
  fireEvent.click(screen.getByRole('button',{name:'返回工作区'}))
  fireEvent.click(await screen.findByRole('button',{name:'Workspace B'}))
  await screen.findByRole('button',{name:'Model B'})
  await act(async()=>late(page('STALE MODEL','SemanticModel')))
  expect(screen.queryByText('STALE MODEL')).not.toBeInTheDocument()
})
it('never publishes a response after unmount and aborts the request',async()=>{
  const invalid=vi.fn()
  let late!:(page:CloudCatalogPage)=>void
  vi.mocked(api.readCloudWorkspaces).mockImplementation(()=>new Promise(resolve=>{late=resolve}))
  const result=render(<CloudCatalogPicker onSelect={vi.fn()} onClose={vi.fn()} onFailure={invalid} />)
  await waitFor(()=>expect(api.readCloudWorkspaces).toHaveBeenCalledOnce())
  const signal=vi.mocked(api.readCloudWorkspaces).mock.calls[0][2]
  result.unmount()
  expect(signal?.aborted).toBe(true)
  await act(async()=>late(page('LATE','Workspace')))
  expect(invalid).not.toHaveBeenCalled()
})

it('keeps 1000+ resources paged with at most 50 visible rows and server search',async()=>{
  const resources=Array.from({length:1200},(_,i)=>({key:`model-${i}`,display_name:`Model ${i}`,kind:'SemanticModel' as const}))
  vi.mocked(api.readCloudResources).mockImplementation(async(_workspace,_kind,query,cursor)=>({
    ...page('','SemanticModel'),items:query ? resources.filter(item=>item.display_name===query) : resources.slice(cursor ? 50 : 0,cursor ? 100 : 50),
    partial:!query,next_cursor:query ? null : 'next',
  }))
  render(<CloudCatalogPicker onSelect={vi.fn()} onClose={vi.fn()} onFailure={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button',{name:'Workspace A'}))
  await screen.findByRole('button',{name:'Model 0'})
  expect(screen.getAllByRole('button',{name:/^Model /})).toHaveLength(50)
  fireEvent.click(screen.getByRole('button',{name:'下一页'}))
  await screen.findByRole('button',{name:'Model 50'})
  expect(screen.getAllByRole('button',{name:/^Model /})).toHaveLength(50)
  fireEvent.change(screen.getByRole('searchbox',{name:'搜索资源'}),{target:{value:'Model 1199'}})
  await screen.findByRole('button',{name:'Model 1199'})
  expect(screen.getAllByRole('button',{name:/^Model /})).toHaveLength(1)
  expect(api.readCloudResources).toHaveBeenCalledTimes(3)
})
