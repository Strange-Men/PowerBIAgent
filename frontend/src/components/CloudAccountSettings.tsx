import { useEffect, useRef, useState } from 'react'
import { ApiError, readCloudCatalog, readCloudStatus } from '../api/client'
import type { AccountActions } from '../types'

export function CloudAccountSettings({account}: {account: AccountActions}) {
  const [tab, setTab] = useState<'account' | 'data'>('account')
  const [info, setInfo] = useState<{count:number;partial:boolean;selected:string | null} | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(false)
  const epoch = useRef(0)
  const abort = useRef<AbortController | null>(null)
  useEffect(() => () => { epoch.current += 1; abort.current?.abort() }, [])

  const load = async () => {
    setTab('data'); setLoading(true); setError(false); setInfo(null)
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
      setInfo({count:catalog.items.length,partial:catalog.status === 'partial',
        selected:catalog.items.find(item => item.key === status.selected_model_key)?.display_name || null})
      window.dispatchEvent(new Event('powerbiagent-cloud-catalog-updated'))
    } catch (caught) {
      if (current === epoch.current) {
        setError(true)
        if (caught instanceof ApiError && caught.status===401) account.refresh?.()
      }
    } finally {
      if (current === epoch.current) setLoading(false)
    }
  }

  const accountTab = () => {
    epoch.current += 1; abort.current?.abort(); setLoading(false); setTab('account')
  }
  return <div className="settings-layout">
    <nav className="settings-nav" aria-label="设置分类">
      <button type="button" className={tab === 'account' ? 'is-active' : ''} onClick={accountTab}>账户</button>
      <button type="button" className={tab === 'data' ? 'is-active' : ''} onClick={() => void load()}>数据与模型</button>
    </nav>
    <div className="settings-content"><section className="settings-intro account-settings">
      {tab === 'account' ? <><h3>账户</h3><dl className="account-details">
        <dt>姓名</dt><dd>{account.session.display_name}</dd>
        <dt>用户名</dt><dd>{account.session.preferred_username || '未提供'}</dd>
        <dt>登录状态</dt><dd>{account.session.authenticated ? '已登录' : '未登录'}</dd>
      </dl><button type="button" onClick={() => void account.logout()}>退出</button></>
        : <><h3>数据与模型</h3>
          {loading ? <p role="status">正在加载云端数据模型…</p> : null}
          {error ? <p role="alert">暂时无法加载目录，请重试。</p> : null}
          {info ? <><p>当前账号可访问 {info.count} 个已验证模型。</p>
            {info.partial ? <p>部分模型可能未包含在目录中。</p> : null}
            <p>{info.selected || '尚未选择模型，请在对话输入区显式选择。'}</p></> : null}
          <button type="button" disabled={loading} onClick={() => void load()}>刷新目录</button>
        </>}
    </section></div>
  </div>
}
