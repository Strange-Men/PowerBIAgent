/// <reference types="node" />
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import path from 'node:path'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { CloudWorkspace } from './CloudWorkspace'
import type { AuthSession } from '../types'

it('uses real API client and native Cloud routes through offline factual host', async () => {
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
  let ready!: (session: AuthSession) => void
  const sessionPromise = new Promise<AuthSession>(resolve => { ready = resolve })
  const lines = createInterface({ input: child.stdout })
  lines.on('line', line => {
    const value = JSON.parse(line)
    if (value.ready) ready(value.session)
    else {
      pending.get(value.id)?.(new Response(value.body, { status: value.status, headers: value.headers }))
      pending.delete(value.id)
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
      requests.push(input)
      child.stdin.write(JSON.stringify({ id, path: input, method: init?.method || 'GET',
        headers: { Origin: 'http://localhost:5173', ...init?.headers }, body: init?.body }) + '\n')
    }))
    const account = { session, state: 'SIGNED_IN' as const, login: vi.fn(), logout: vi.fn() }
    render(<CloudWorkspace session={session} account={account} onAuthInvalid={vi.fn()} />)
    await screen.findByText('合成销售模型', {}, { timeout: 10000 })
    const send = async (message: string) => {
      const input = screen.getByRole('textbox', { name: '询问你的 Power BI 数据' })
      fireEvent.change(input, { target: { value: message } })
      await waitFor(() => expect(screen.getByRole('button', { name: '发送' })).toBeEnabled())
      fireEvent.click(screen.getByRole('button', { name: '发送' }))
    }
    await send('查询 Total Sales')
    await screen.findByText(/1,?200\.5/, {}, { timeout: 10000 })
    fireEvent.click(screen.getByRole('button', { name: '打开数据与报表选项' }))
    fireEvent.click(await screen.findByRole('button', { name: /简易销售分析模板/ }))
    await send('生成销售分析报表')
    const link = await screen.findByRole('link', { name: /查看报表/ }, { timeout: 10000 })
    expect(link.getAttribute('href')).toMatch(/^\/api\/v1\/cloud\/reports\//)
    const artifact = await fetch(link.getAttribute('href')!)
    expect(artifact.status).toBe(200)
    expect(await artifact.text()).toMatch(/1,?200\.5/)
    expect(artifact.headers.get('content-security-policy')).toContain('sandbox')
    const download=await fetch(link.getAttribute('href')!+'/download')
    expect(download.status).toBe(200)
    expect(download.headers.get('content-disposition')).toContain('attachment')
    fireEvent.click(screen.getByRole('button',{name:'搜索聊天'}))
    fireEvent.change(screen.getByRole('textbox',{name:'搜索标题、问题或回答'}),{target:{value:'Total Sales'}})
    fireEvent.click(screen.getByRole('button',{name:'执行搜索'}))
    await waitFor(()=>expect(requests.some(url=>url.includes('q=Total+Sales'))).toBe(true))
    fireEvent.click(screen.getByRole('button',{name:'关闭搜索'}))
    // Existing Settings resource UI must use the same formal Cloud source.
    fireEvent.click(screen.getByRole('button',{name:session.display_name!}))
    fireEvent.click(screen.getByRole('menuitem',{name:'设置'}))
    fireEvent.click(await screen.findByRole('button',{name:'对话管理'}))
    await screen.findByRole('checkbox',{name:/选择对话/})
    expect(requests.some(url=>url.includes('/api/v1/cloud/history?status=active'))).toBe(true)
    vi.spyOn(window,'prompt').mockReturnValue('合成重命名')
    fireEvent.click(screen.getByRole('button',{name:'重命名'}))
    await screen.findByRole('checkbox',{name:'选择对话：合成重命名'})
    expect(screen.getByRole('button',{name:'合成重命名'})).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox',{name:'选择对话：合成重命名'}))
    fireEvent.click(screen.getByRole('button',{name:'批量归档'}))
    await waitFor(()=>expect(screen.queryByRole('checkbox',{name:'选择对话：合成重命名'})).not.toBeInTheDocument())
    fireEvent.click(screen.getByRole('button',{name:'已归档'}))
    fireEvent.click(await screen.findByRole('checkbox',{name:'选择对话：合成重命名'}))
    fireEvent.click(screen.getAllByRole('button',{name:'批量恢复'})[0])
    await waitFor(()=>expect(screen.queryByRole('checkbox',{name:'选择对话：合成重命名'})).not.toBeInTheDocument())
    fireEvent.click(screen.getByRole('button',{name:'报表管理'}))
    fireEvent.click(await screen.findByRole('checkbox',{name:/选择报表/}))
    vi.spyOn(window,'confirm').mockReturnValue(true)
    fireEvent.click(screen.getByRole('button',{name:'批量删除'}))
    await waitFor(()=>expect(screen.queryByRole('checkbox',{name:/选择报表/})).not.toBeInTheDocument())
    expect((await fetch(link.getAttribute('href')!+'/download')).status).toBe(404)
    fireEvent.click(screen.getByRole('button',{name:'关闭设置'}))
    fireEvent.click(screen.getByRole('button', { name: '新聊天' }))
    await waitFor(() => expect(screen.queryByRole('link', { name: /查看报表/ })).not.toBeInTheDocument())
    expect(requests).toContain('/api/v1/cloud/chat')
    expect(requests.some(url => url.startsWith('/api/v1/cloud/history'))).toBe(true)
  } finally {
    vi.unstubAllGlobals()
    child.stdin.write(JSON.stringify({ close: true }) + '\n')
    await exit
    lines.close()
  }
}, 60000)
