import { useTranslation } from 'react-i18next'
import { tr, publicText } from '../i18n'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, readCloudCatalog, readCloudStatus } from '../api/client'
import type { AccountActions } from '../types'
import { cloudDenialMessage, publicFailureMessage } from '../failure'
import { GeneralSettings } from './GeneralSettings'

export function CloudAccountSettings({account,panel}: {account: AccountActions;panel?:'account'|'data'}) {
  useTranslation()
  const [tab, setTab] = useState<'general' | 'account' | 'data'>('general')
  const active=panel||tab
  const refresh=account.refresh
  const [info, setInfo] = useState<{count:number;partial:boolean;product:boolean;selected:string | null} | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const epoch = useRef(0)
  const abort = useRef<AbortController | null>(null)
  useEffect(() => () => { epoch.current += 1; abort.current?.abort() }, [])

  const fetchData = useCallback(async () => {
    const current = ++epoch.current
    abort.current?.abort()
    const controller = new AbortController()
    abort.current = controller
    try {
      const catalog = await readCloudCatalog(controller.signal)
      if (current !== epoch.current) return
      const status = await readCloudStatus(controller.signal)
      if (current !== epoch.current) return
      if (catalog.status === 'error' || catalog.status === 'forbidden') throw new Error('Catalog unavailable')
      setInfo({count:catalog.items.length,partial:catalog.status === 'partial',product:catalog.product_mode === true,
        selected:catalog.items.find(item => item.key === status.selected_model_key)?.display_name || null})
      window.dispatchEvent(new Event('powerbiagent-cloud-catalog-updated'))
    } catch (caught) {
      if (current === epoch.current) {
        setError(caught instanceof ApiError && caught.denialReason ? cloudDenialMessage(caught.denialReason)
          : caught instanceof ApiError && caught.failure ? publicFailureMessage(caught.failure)
          : tr('auth:cannotLoadTheCatalogTryAgain'))
        if (caught instanceof ApiError && caught.status===401) refresh?.()
      }
    } finally {
      if (current === epoch.current) setLoading(false)
    }
  },[refresh])
  const load=()=>{
    setTab('data');setLoading(true);setError(null);setInfo(null)
    void fetchData()
  }

  const selectTab = (next:'general'|'account') => {
    epoch.current += 1; abort.current?.abort(); setLoading(false); setTab(next)
  }
  const content=active==='general' ? <GeneralSettings /> : <section className="settings-intro account-settings">
      {active === 'account' ? <><h3>{tr('auth:account')}</h3><dl className="account-details">
        <dt>{tr('auth:name')}</dt><dd>{account.session.display_name}</dd>
        <dt>{tr('auth:username')}</dt><dd>{account.session.preferred_username || tr('auth:notProvided')}</dd>
        <dt>{tr('auth:signinStatus')}</dt><dd>{account.session.authenticated ? tr('auth:signedIn') : tr('auth:signedOut')}</dd>
      </dl><button type="button" onClick={() => void account.logout()}>{tr('auth:signOut')}</button></>
        : <><h3>{tr('auth:dataAndModels')}</h3>
          {loading ? <p role="status">{tr('auth:loadingCloudDataModels')}</p> : null}
          {error ? <p role="alert">{publicText(error)}</p> : null}
          {info ? <><p>{info.product ? tr('auth:browseModelsInComposer') : tr('resources:verifiedModelCount', {count:info.count})}</p>
            {info.partial && !info.product ? <p>{tr('auth:someModelsMayNotBeIncludedInThisCatalog')}</p> : null}
            <p>{info.selected || tr('auth:noModelSelectedChooseAModelInTheComposer')}</p></> : null}
          <button type="button" disabled={loading} onClick={() => void load()}>{tr('auth:refreshCatalog')}</button>
        </>}
    </section>
  if(panel)return content
  return <div className="settings-layout">
    <nav className="settings-nav" aria-label={tr('auth:settingsCategories')}>
      <button type="button" className={tab==='general'?'is-active':''} onClick={()=>selectTab('general')}>{tr('resources:general')}</button>
      {account.session.authenticated ? <>
        <button type="button" className={tab==='account'?'is-active':''} onClick={()=>selectTab('account')}>{tr('auth:account')}</button>
        <button type="button" className={tab==='data'?'is-active':''} onClick={()=>void load()}>{tr('auth:dataAndModels')}</button>
      </> : null}
    </nav>
    <div className="settings-content">{content}</div>
  </div>
}
