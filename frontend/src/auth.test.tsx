import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { App } from './App'
import { useAuth } from './hooks/useAuth'

const product = vi.hoisted(() => vi.fn(() => { throw new Error('Product hook mounted in ENTRA_BFF') }))
vi.mock('./hooks/usePowerBIAgent', () => ({ usePowerBIAgent: product }))

const signedIn = { identity_mode: 'ENTRA_BFF', authenticated: true, state: 'SIGNED_IN',
  display_name: 'Synthetic A', preferred_username: 'a@example.invalid', csrf_token: 'synthetic-csrf', expires_in: 3600 }
const signedOut = { identity_mode: 'ENTRA_BFF', authenticated: false, state: 'SIGNED_OUT',
  failure: { code: 'AUTH_REQUIRED', stage: 'auth', retryable: false, recovery_action: 'login' } }

let fetchMock: ReturnType<typeof vi.fn>
let channels: FakeChannel[]
class FakeChannel {
  onmessage: ((event: MessageEvent) => void) | null = null
  postMessage = vi.fn()
  close = vi.fn()
  constructor() { channels.push(this) }
}
const response = (body: object, status = 200) => new Response(JSON.stringify(body), { status, headers: {'Content-Type': 'application/json'} })

beforeEach(() => {
  channels = []
  product.mockClear()
  fetchMock = vi.fn().mockResolvedValue(response(signedOut, 401))
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('BroadcastChannel', FakeChannel)
})
afterEach(() => vi.unstubAllGlobals())

it('signed out bootstrap performs ZERO product API access', async () => {
  render(<App />)
  await waitFor(() => expect(screen.getByRole('button', {name: '使用 Microsoft 登录'})).toBeEnabled())
  expect(screen.getByRole('button', {name: '使用 Microsoft 登录'})).toBeVisible()
  expect(product).not.toHaveBeenCalled()
  expect(fetchMock.mock.calls.map(c => c[0])).toEqual(['/auth/session'])
})

it('signed in account/settings expose safe fields and perform ZERO resource bootstrap', async () => {
  fetchMock.mockResolvedValue(response(signedIn))
  render(<App />)
  fireEvent.click(await screen.findByRole('button', {name: 'Synthetic A'}))
  fireEvent.click(screen.getByRole('menuitem', {name: '设置'}))
  expect(screen.getByRole('dialog')).toBeVisible()
  expect(screen.getByText('a@example.invalid', {selector:'dd'})).toBeVisible()
  expect(screen.queryByText('数据模型')).not.toBeInTheDocument()
  expect(product).not.toHaveBeenCalled()
  expect(fetchMock.mock.calls.every(c => c[0] === '/auth/session')).toBe(true)
  expect(document.body.textContent).not.toMatch(/tenant|scope|claims|client.secret|synthetic-csrf/i)
})

it('logout uses CSRF, clears account and broadcasts only invalidation', async () => {
  fetchMock.mockResolvedValueOnce(response(signedIn)).mockResolvedValue(response({authenticated:false}))
  const {result} = renderHook(() => useAuth())
  await waitFor(() => expect(result.current.session?.authenticated).toBe(true))
  await act(async () => result.current.logout())
  expect(result.current.session?.authenticated).toBe(false)
  expect(fetchMock.mock.calls[1][0]).toBe('/auth/logout')
  expect(fetchMock.mock.calls[1][1].headers['X-CSRF-Token']).toBe('synthetic-csrf')
  expect(channels[0].postMessage).toHaveBeenCalledWith('session-invalidated')
})

it('cross tab logout invalidates state without transmitting identity', async () => {
  fetchMock.mockResolvedValue(response(signedIn))
  const {result} = renderHook(() => useAuth())
  await waitFor(() => expect(result.current.session?.authenticated).toBe(true))
  act(() => channels[0].onmessage?.(new MessageEvent('message', {data:'session-invalidated'})))
  expect(result.current.session?.authenticated).toBe(false)
  expect(result.current.state).toBe('SIGNED_OUT')
})

it('late A response cannot overwrite B session generation', async () => {
  let resolveA!: (r: Response) => void
  fetchMock.mockReturnValueOnce(new Promise<Response>(resolve => {resolveA = resolve}))
  const {result} = renderHook(() => useAuth())
  act(() => channels[0].onmessage?.(new MessageEvent('message', {data:'session-invalidated'})))
  fetchMock.mockResolvedValue(response({...signedIn, display_name:'Synthetic B'}))
  await act(async () => result.current.refresh())
  await act(async () => resolveA(response(signedIn)))
  expect(result.current.session?.display_name).toBe('Synthetic B')
})

it('failed logout freezes old identity and offers retry', async () => {
  fetchMock.mockResolvedValueOnce(response(signedIn)).mockRejectedValue(new Error('offline'))
  const {result} = renderHook(() => useAuth())
  await waitFor(() => expect(result.current.session?.authenticated).toBe(true))
  await act(async () => result.current.logout())
  expect(result.current.session?.authenticated).toBe(false)
  expect(result.current.logoutPending).toBe(true)
  expect(result.current.state).toBe('AUTH_ERROR')
})

it('session expiry clears identity and requires relogin', async () => {
  fetchMock.mockResolvedValueOnce(response(signedIn)).mockResolvedValue(response({...signedOut, state:'SESSION_EXPIRED',
    failure:{...signedOut.failure, code:'AUTH_EXPIRED', recovery_action:'relogin'}}, 401))
  const {result} = renderHook(() => useAuth())
  await waitFor(() => expect(result.current.state).toBe('SIGNED_IN'))
  await act(async () => result.current.refresh())
  expect(result.current.state).toBe('SESSION_EXPIRED')
  expect(result.current.session?.authenticated).toBe(false)
})
