/// <reference types="node" />
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import path from 'node:path'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { tr, setLocale } from '../i18n'
import { CloudWorkspace } from './CloudWorkspace'
import type { AuthSession } from '../types'

it.each(['zh-CN','en-US'] as const)('uses native Cloud routes and resource lifecycle in %s', async (locale) => {
  await setLocale(locale)
  const repo = path.resolve(process.cwd(), '..')
  const python = process.env.PBI_SYNTHETIC_PYTHON || 'python'
  const child = spawn(python, ['-u', 'backend/tests/cloud_factual_bridge.py'], {
    cwd: repo, env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
    stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
  })
  let serial = 0
  let stderr = ''
  child.stderr.on('data', chunk => { stderr += String(chunk) })
  const pending = new Map<number, (value: Response) => void>()
  const deletionAck = new Map<number, (status: number) => void>()
  let reportDeletion!: (status: number) => void
  const reportDeleted = new Promise<number>(resolve=>{reportDeletion=resolve})
  let ready!: (session: AuthSession) => void
  const sessionPromise = new Promise<AuthSession>(resolve => { ready = resolve })
  const lines = createInterface({ input: child.stdout })
  lines.on('line', line => {
    const value = JSON.parse(line)
    if (value.ready) ready(value.session)
    else {
      pending.get(value.id)?.(new Response(value.body, { status: value.status, headers: value.headers }))
      pending.delete(value.id)
      deletionAck.get(value.id)?.(value.status)
      deletionAck.delete(value.id)
    }
  })
  const exit = new Promise<void>((resolve, reject) => {
    child.on('error', reject)
    child.on('exit', code => code === 0 ? resolve() : reject(new Error(`Synthetic host ${code}: ${stderr}`)))
  })
  try {
    const session = await Promise.race([sessionPromise, exit.then(() => { throw new Error('Host exited before ready') })])
    const requests: string[] = []
    vi.stubGlobal('fetch', (input: string, init?: RequestInit) => new Promise<Response>(resolve => {
      const id = ++serial
      pending.set(id, resolve)
      if (init?.method==='DELETE' && input.startsWith('/api/v1/cloud/reports/')) deletionAck.set(id,reportDeletion)
      if (init?.method==='POST' && input==='/api/v1/cloud/resources/batch'
          && typeof init.body==='string' && JSON.parse(init.body).kind==='reports'
          && JSON.parse(init.body).action==='delete') deletionAck.set(id,reportDeletion)
      requests.push(input)
      child.stdin.write(JSON.stringify({ id, path: input, method: init?.method || 'GET',
        headers: { Origin: 'http://localhost:5173', ...init?.headers }, body: init?.body }) + '\n')
    }))
    const account = { session, state: 'SIGNED_IN' as const, login: vi.fn(), logout: vi.fn() }
    render(<CloudWorkspace session={session} account={account} onAuthInvalid={vi.fn()} />)
    await screen.findByText('合成销售模型', {}, { timeout: 10000 })
    const send = async (message: string) => {
      const input = screen.getByRole('textbox', { name: tr('composer:askAboutYourPowerBiData') })
      fireEvent.change(input, { target: { value: message } })
      await waitFor(() => expect(screen.getByRole('button', { name: tr('composer:send') })).toBeEnabled())
      fireEvent.click(screen.getByRole('button', { name: tr('composer:send') }))
    }
    await send('查询 Total Sales')
    await screen.findByText(/1,?200\.5/, {}, { timeout: 10000 })
    const factualRoutes=requests.filter(url=>!url.includes('/presentations/')).slice()
    await act(async()=>{await setLocale(locale==='zh-CN'?'en-US':'zh-CN')})
    await waitFor(()=>expect(requests.some(url=>url.includes('/presentations/'))).toBe(true))
    await act(async()=>{await setLocale(locale)})
    await screen.findByText(/1,?200\.5/, {}, { timeout: 10000 })
    expect(requests.filter(url=>!url.includes('/presentations/'))).toEqual(factualRoutes)
    fireEvent.click(screen.getByRole('button', { name: tr('composer:openDataAndReportOptions') }))
    fireEvent.click(await screen.findByRole('button', { name: new RegExp(tr('reports:simpleTemplate')) }))
    await send('生成销售分析报表')
    const link = await screen.findByRole('link', { name: tr('reports:viewReport') }, { timeout: 10000 })
    expect(link.getAttribute('href')).toMatch(/^\/api\/v1\/cloud\/reports\//)
    const reportUrl=new URL(link.getAttribute('href')!,'http://localhost:5173')
    const downloadUrl=reportUrl.pathname+'/download'+reportUrl.search
    const artifact = await fetch(link.getAttribute('href')!)
    expect(artifact.status).toBe(200)
    expect(await artifact.text()).toMatch(/1,?200\.5/)
    expect(artifact.headers.get('content-security-policy')).toContain('sandbox')
    const download=await fetch(downloadUrl)
    expect(download.status).toBe(200)
    expect(download.headers.get('content-disposition')).toContain('attachment')
    fireEvent.click(screen.getByRole('button',{name:tr('sidebar:searchChats')}))
    fireEvent.change(screen.getByRole('textbox',{name:tr('sidebar:searchTitlesQuestionsOrAnswers')}),{target:{value:'Total Sales'}})
    fireEvent.click(screen.getByRole('button',{name:tr('sidebar:search')}))
    await waitFor(()=>expect(requests.some(url=>url.includes('q=Total+Sales'))).toBe(true))
    fireEvent.click(screen.getByRole('button',{name:tr('sidebar:closeSearch')}))
    // Existing Settings resource UI must use the same formal Cloud source.
    fireEvent.click(screen.getByRole('button',{name:session.display_name!}))
    fireEvent.click(screen.getByRole('menuitem',{name:tr('resources:settings')}))
    fireEvent.click(await screen.findByRole('button',{name:tr('resources:conversations')}))
    await screen.findByRole('checkbox',{name:new RegExp(tr('resources:selectConversation',{p0:''}))})
    expect(requests.some(url=>url.includes('/api/v1/cloud/history?status=active'))).toBe(true)
    vi.spyOn(window,'prompt').mockReturnValue('合成重命名')
    fireEvent.click(screen.getByRole('button',{name:tr('resources:rename')}))
    await screen.findByRole('checkbox',{name:tr('resources:selectConversation',{p0:'合成重命名'})})
    expect(screen.getByRole('button',{name:'合成重命名'})).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox',{name:tr('resources:selectConversation',{p0:'合成重命名'})}))
    fireEvent.click(screen.getByRole('button',{name:tr('resources:archiveSelected')}))
    await waitFor(()=>expect(screen.queryByRole('checkbox',{name:tr('resources:selectConversation',{p0:'合成重命名'})})).not.toBeInTheDocument())
    fireEvent.click(screen.getByRole('button',{name:tr('resources:archived')}))
    fireEvent.click(await screen.findByRole('checkbox',{name:tr('resources:selectConversation',{p0:'合成重命名'})}))
    fireEvent.click(screen.getAllByRole('button',{name:tr('resources:restoreSelected')})[0])
    await waitFor(()=>expect(screen.queryByRole('checkbox',{name:tr('resources:selectConversation',{p0:'合成重命名'})})).not.toBeInTheDocument())
    fireEvent.click(screen.getByRole('button',{name:tr('resources:reports')}))
    fireEvent.click(await screen.findByRole('checkbox',{name:new RegExp(tr('resources:selectReport',{p0:''}))}))
    vi.spyOn(window,'confirm').mockReturnValue(true)
    fireEvent.click(screen.getByRole('button',{name:tr('resources:deleteSelected')}))
    // The stdio host uses real SQLite/HTML cleanup. Await its commit response,
    // then assert the UI projection; do not use a 1s DOM poll as an API deadline.
    expect(await reportDeleted).toBe(200)
    await waitFor(()=>expect(screen.queryByRole('checkbox',{name:new RegExp(tr('resources:selectReport',{p0:''}))})).not.toBeInTheDocument())
    expect((await fetch(downloadUrl)).status).toBe(404)
    fireEvent.click(screen.getByRole('button',{name:tr('resources:closeSettings')}))
    fireEvent.click(screen.getByRole('button', { name: tr('sidebar:newChat') }))
    await waitFor(() => expect(screen.queryByRole('link', { name: tr('reports:viewReport') })).not.toBeInTheDocument())
    expect(requests).toContain('/api/v1/cloud/chat')
    expect(requests.some(url => url.startsWith('/api/v1/cloud/history'))).toBe(true)
  } finally {
    vi.unstubAllGlobals()
    child.stdin.write(JSON.stringify({ close: true }) + '\n')
    await exit
    lines.close()
  }
}, 60000)
