import { useCallback, useEffect, useRef, useState } from 'react'
import { logoutAuthSession, readAuthSession } from '../api/client'
import type { AuthSession, AuthState } from '../types'

const signedOut: AuthSession = {identity_mode:'ENTRA_BFF', authenticated:false,
  display_name:null, preferred_username:null, state:'SIGNED_OUT', csrf_token:null, expires_in:0}

export function useAuth() {
  const [session, setSession] = useState<AuthSession | null>(null)
  const [state, setState] = useState<AuthState>('SESSION_ESTABLISHING')
  const [generation, setGeneration] = useState(0)
  const [logoutPending, setLogoutPending] = useState(false)
  const epoch = useRef(0)
  const abort = useRef<AbortController | null>(null)
  const channel = useRef<BroadcastChannel | null>(null)
  const csrf = useRef<string | null>(null)
  const frozen = useRef(false)
  const sessionMarker = useRef<string | null>(null)

  const invalidate = useCallback((broadcast: boolean) => {
    epoch.current += 1
    abort.current?.abort()
    setGeneration(epoch.current)
    setSession(signedOut)
    setState('SIGNED_OUT')
    if (broadcast) channel.current?.postMessage('session-invalidated')
  }, [])

  const refresh = useCallback(async () => {
    if (frozen.current) return
    const current = ++epoch.current
    abort.current?.abort()
    const controller = new AbortController()
    abort.current = controller
    try {
      const next = await readAuthSession(controller.signal)
      if (current !== epoch.current) return
      csrf.current = next.csrf_token
      const marker = next.csrf_token || next.identity_mode + next.state
      if (marker !== sessionMarker.current) {
        sessionMarker.current = marker
        setGeneration(current)
      }
      setSession(next)
      setState(next.state === 'LOCAL_DEV' ? 'SIGNED_OUT' : next.state)
    } catch {
      if (current !== epoch.current) return
      setSession(signedOut)
      setState('AUTH_ERROR')
      setGeneration(current)
    }
  }, [])

  useEffect(() => {
    if (typeof BroadcastChannel !== 'undefined') {
      const active = new BroadcastChannel('powerbiagent-auth')
      channel.current = active
      active.onmessage = (event) => {
        if (event.data === 'session-invalidated') {
          csrf.current = null
          invalidate(false)
        }
      }
    }
    void refresh()
    return () => {
      epoch.current += 1
      abort.current?.abort()
      channel.current?.close()
      channel.current = null
    }
  }, [invalidate, refresh])

  useEffect(() => {
    if (session?.identity_mode !== 'ENTRA_BFF' || !session.authenticated) return
    const timer = window.setTimeout(() => void refresh(), Math.min(session.expires_in * 1000, 60000))
    const focus = () => void refresh()
    window.addEventListener('focus', focus)
    return () => { window.clearTimeout(timer); window.removeEventListener('focus', focus) }
  }, [session, refresh])

  const logout = useCallback(async () => {
    const proof = csrf.current
    frozen.current = true
    setLogoutPending(true)
    invalidate(true)
    const current = epoch.current
    try {
      if (!proof) throw new Error('Logout proof unavailable')
      await logoutAuthSession(proof)
      if (current !== epoch.current) return
      csrf.current = null
      frozen.current = false
      setLogoutPending(false)
    } catch {
      if (current !== epoch.current) return
      setState('AUTH_ERROR')
    }
  }, [invalidate])

  const login = useCallback(() => {
    if (frozen.current) return
    epoch.current += 1
    abort.current?.abort()
    setState('AUTHENTICATING')
    window.location.assign('/auth/login')
  }, [])

  return {session, state, generation, login, logout, logoutPending, refresh}
}
