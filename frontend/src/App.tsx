import { useEffect, useState } from 'react'
import { Composer } from './components/Composer'
import { ConversationView } from './components/ConversationView'
import { Sidebar } from './components/Sidebar'
import { usePowerBIAgent } from './hooks/usePowerBIAgent'
import { useAuth } from './hooks/useAuth'
import type { BatchOperationResult } from './types'

const unavailable = async () => { throw new Error('当前暂不开放组织数据访问。') }
const emptyBatch = async (): Promise<BatchOperationResult> => ({succeededIds:[], failed:[]})

export function App() {
  const auth = useAuth()
  const [collapsed, setCollapsed] = useState(() =>
    typeof window.matchMedia === 'function' ? window.matchMedia('(max-width: 760px)').matches : false)
  if (auth.session?.identity_mode === 'LOCAL_DEV') return <LocalWorkspace />
  return <div className="app-shell">
    <Sidebar key={auth.generation} collapsed={collapsed} activeConversationId={null} runtimeMode="real"
      conversations={[]} reports={[]} error={null} onToggle={() => setCollapsed(v => !v)} onNewChat={() => {}}
      onOpenConversation={() => {}} onSearch={unavailable} onRename={unavailable} onArchive={unavailable}
      onRestore={unavailable} onDelete={unavailable} onDeleteReport={unavailable} onArchiveReport={unavailable}
      onRenameReport={unavailable} onBulkDeleteConversations={emptyBatch} onBulkArchiveConversations={emptyBatch}
      onBulkRestoreConversations={emptyBatch} onBulkDeleteReports={emptyBatch} onBulkArchiveReports={emptyBatch}
      onBulkRestoreReports={emptyBatch} account={{session:auth.session || {
        identity_mode:'ENTRA_BFF', authenticated:false, display_name:null, preferred_username:null,
        csrf_token:null, state:auth.state, expires_in:0}, state:auth.state, login:auth.login, logout:auth.logout}} />
    <main className="chat-main auth-welcome">
      <h1>{auth.session?.authenticated ? '欢迎回来' : '使用组织 Power BI 数据进行问答'}</h1>
      {auth.state === 'SESSION_ESTABLISHING' || auth.state === 'AUTHENTICATING'
        ? <p role="status">{auth.state === 'AUTHENTICATING' ? '正在登录…' : '正在确认登录状态…'}</p>
        : auth.session?.authenticated ? <p>你已登录。组织数据功能将在后续版本开放。</p>
        : <p role={auth.state === 'SIGNED_OUT' ? 'status' : 'alert'}>{
          auth.logoutPending ? '退出尚未完成，请重试。' : auth.state === 'SESSION_EXPIRED' ? '登录已过期，请重新登录。'
          : auth.state === 'CONSENT_REQUIRED' ? '需要批准才能继续，请登录或联系管理员。'
          : auth.state === 'AUTH_ERROR' ? '登录未完成，请重试或联系管理员。' : '登录后查看你的账户。'}</p>}
      {auth.logoutPending ? <button type="button" onClick={() => void auth.logout()}>重试退出</button> : null}
    </main>
  </div>
}

function LocalWorkspace() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(max-width: 760px)').matches
      : false,
  )
  const app = usePowerBIAgent()

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const media = window.matchMedia('(max-width: 760px)')
    const respond = (event: MediaQueryListEvent) => setSidebarCollapsed(event.matches)
    media.addEventListener('change', respond)
    return () => media.removeEventListener('change', respond)
  }, [])

  return (
    <div className="app-shell">
      <Sidebar
        collapsed={sidebarCollapsed}
        activeConversationId={app.activeConversationId}
        runtimeMode={app.effectiveRuntimeMode}
        conversations={app.recentConversations}
        reports={app.recentReports}
        error={app.sidebarError}
        onToggle={() => setSidebarCollapsed((collapsed) => !collapsed)}
        onNewChat={app.startNewChat}
        onOpenConversation={(conversation) => void app.openConversation(conversation)}
        onSearch={app.search}
        onRename={app.rename}
        onArchive={app.archive}
        onRestore={app.restore}
        onDelete={app.remove}
        onDeleteReport={app.removeReport}
        onArchiveReport={app.archiveReport}
        onRenameReport={app.renameReport}
        onBulkDeleteConversations={app.bulkRemoveConversations}
        onBulkArchiveConversations={app.bulkArchiveConversations}
        onBulkRestoreConversations={app.bulkRestoreConversations}
        onBulkDeleteReports={app.bulkRemoveReports}
        onBulkArchiveReports={app.bulkArchiveReports}
        onBulkRestoreReports={app.bulkRestoreReports}
      />
      <main className="chat-main">
        {app.messages.length > 0 ? (
          <header className="conversation-header">
            <h1>{app.title}</h1>
          </header>
        ) : null}
        <ConversationView
          messages={app.messages}
          sending={app.sending}
          loadingConversation={app.loadingConversation}
          restored={app.hasRestoredHistory}
        />
        <Composer
          sending={app.sending}
          semanticModel={app.selectedSemanticModel}
          semanticModelOptions={app.semanticModelOptions}
          loadingSemanticModels={app.loadingSemanticModels}
          semanticModelError={app.semanticModelError}
          semanticModelCompatibilityNotice={app.semanticModelCompatibilityNotice}
          reportTemplate={app.selectedReportTemplate}
          reportTemplateOptions={app.reportTemplateOptions}
          loadingReportTemplates={app.loadingReportTemplates}
          reportTemplateError={app.reportTemplateError}
          llmProfile={app.selectedLLMProfile}
          llmProfileOptions={app.llmProfileOptions}
          loadingLLMProfiles={app.loadingLLMProfiles}
          llmProfileError={app.llmProfileError}
          onSemanticModelChange={app.setSelectedSemanticModel}
          onRefreshSemanticModels={app.refreshSemanticModels}
          onReportTemplateChange={app.setSelectedReportTemplate}
          onLLMProfileChange={app.setSelectedLLMProfile}
          onSend={app.submitMessage}
        />
      </main>
    </div>
  )
}
