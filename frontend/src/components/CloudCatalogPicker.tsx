import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react'
import { ApiError, readCloudResources, readCloudWorkspaces } from '../api/client'
import { cloudFailureAction, publicFailureMessage } from '../failure'
import { publicText, tr } from '../i18n'
import type { CloudCatalogEntry, CloudCatalogPage } from '../cloudTypes'
import type { CatalogOption } from '../types'

/** Reuses Composer's existing compact menu, search, row and status classes. */
export function CloudCatalogPicker({onSelect, onClose, onFailure, onOpenLink}: {
  onSelect: (option: CatalogOption) => Promise<boolean>
  onClose: () => void
  onFailure: (error: unknown) => void
  onOpenLink?: (url: string) => Promise<boolean>
}) {
  useTranslation()
  const [workspace, setWorkspace] = useState<CloudCatalogEntry | null>(null)
  const [kind, setKind] = useState<'SemanticModel'|'Report'>('SemanticModel')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState<CloudCatalogPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [selecting, setSelecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [link, setLink] = useState('')
  const [linkOpen, setLinkOpen] = useState(false)
  const epoch = useRef(0)
  const active = useRef<AbortController | null>(null)
  const cancelActive = useCallback(() => { epoch.current++; active.current?.abort() }, [])
  const invalidate = () => { cancelActive(); setPage(null); setError(null) }
  const load = useCallback(async (cursor?: string) => {
    active.current?.abort()
    const current = ++epoch.current, controller = new AbortController()
    active.current = controller
    setLoading(true); setError(null)
    try {
      const next = workspace
        ? await readCloudResources(workspace.key, kind, query, cursor, controller.signal)
        : await readCloudWorkspaces(query, cursor, controller.signal)
      if (current !== epoch.current || controller.signal.aborted) return
      setPage(next)
    } catch (caught) {
      if (current !== epoch.current || controller.signal.aborted) return
      if (caught instanceof ApiError && cloudFailureAction(caught) === 'auth') onFailure(caught)
      setError(caught instanceof ApiError && caught.failure ? publicFailureMessage(caught.failure)
        : tr('composer:catalogUnavailable'))
    } finally { if (current === epoch.current) setLoading(false) }
  }, [workspace, kind, query, onFailure])
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), query ? 180 : 0)
    return () => { window.clearTimeout(timer); cancelActive() }
  }, [load, query, cancelActive])

  const choose = async (entry: CloudCatalogEntry) => {
    if (entry.kind === 'Workspace') {
      invalidate(); setWorkspace(entry); setQuery(''); setKind('SemanticModel'); return
    }
    setSelecting(true)
    try {
      const selected = await onSelect({key:entry.key,label:entry.display_name,
        description:workspace?.display_name || '',compatible:true,selectable:true})
      if (selected) onClose()
    } finally { setSelecting(false) }
  }
  return <div className="menu-group" aria-busy={loading || selecting}>
    {onOpenLink ? <>
      <button type="button" className="menu-option" disabled={selecting} onClick={()=>setLinkOpen(!linkOpen)}>{tr('composer:openResourceLink')}</button>
      {linkOpen ? <div className="menu-group">
        <input className="catalog-filter" type="url" maxLength={2048} value={link} disabled={selecting}
          aria-label={tr('composer:resourceLink')} onChange={event=>setLink(event.target.value)}/>
        <p className="menu-empty-state">{tr('composer:resourceLinkHint')}</p>
        <button className="catalog-refresh" type="button" disabled={!link.trim() || selecting} onClick={()=>{
          setSelecting(true)
          void onOpenLink(link.trim()).then(ok=>{if(ok) onClose()}).finally(()=>setSelecting(false))
        }}>{tr('composer:openResource')}</button>
      </div> : null}
    </> : null}
    <div className="menu-heading">
      {workspace ? <button className="catalog-refresh" type="button" aria-label={tr('composer:backToWorkspaces')}
        disabled={selecting} onClick={()=>{invalidate();setWorkspace(null);setQuery('')}}><ChevronLeft size={16}/>{publicText(workspace.display_name)}</button>
        : <span className="menu-label">{tr('composer:workspaces')}</span>}
      <button className="catalog-refresh" type="button" disabled={loading || selecting}
        aria-label={tr('composer:refreshDataModels')} onClick={()=>void load()}><RefreshCw size={14}/>{tr('composer:refresh')}</button>
    </div>
    {workspace ? <div className="menu-heading">
      {(['SemanticModel','Report'] as const).map(value=><button className="catalog-refresh" type="button" key={value}
        aria-pressed={kind===value} disabled={selecting} onClick={()=>{if (kind===value) return;invalidate();setKind(value);setQuery('')}}>
        {value==='SemanticModel' ? tr('composer:semanticModels') : tr('composer:reports')}</button>)}
    </div> : null}
    <input className="catalog-filter" type="search" maxLength={100} disabled={selecting} value={query}
      aria-label={workspace ? tr('composer:searchResources') : tr('composer:searchWorkspaces')}
      placeholder={workspace ? tr('composer:searchResources') : tr('composer:searchWorkspaces')}
      onChange={event=>{invalidate();setQuery(event.target.value)}} />
    {loading ? <p className="menu-empty-state" role="status">{tr('composer:catalogLoading')}</p> : null}
    {error ? <p className="menu-empty-state" role="alert">{publicText(error)}</p> : null}
    {!loading && !error && page?.items.length===0 ? <p className="menu-empty-state">
      {!workspace && !query && !page.next_cursor ? tr('composer:noWorkspaceAccess') : tr('composer:noResourceMatch')}</p> : null}
    {!loading && page?.items.map(entry=><button type="button" className="menu-option" key={entry.key}
      disabled={selecting} onClick={()=>void choose(entry)}><span><strong>{publicText(entry.display_name)}</strong></span>
      {entry.kind==='Workspace' ? <ChevronRight size={16}/> : null}</button>)}
    {!loading && page?.next_cursor ? <button className="catalog-refresh" type="button" disabled={selecting}
      onClick={()=>void load(page.next_cursor || undefined)}>{tr('composer:nextPage')}</button> : null}
    {!loading && page ? <p className="menu-empty-state">{page.partial ? tr('composer:catalogPartial') : tr('composer:catalogCoverage')}</p> : null}
  </div>
}
