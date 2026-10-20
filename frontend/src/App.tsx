import { useTranslation } from 'react-i18next'
import { tr, publicText } from './i18n'
import { useEffect, useState } from 'react'
import { Composer } from './components/Composer'
import { ConversationView } from './components/ConversationView'
import { Sidebar } from './components/Sidebar'
import { CloudWorkspace } from './components/CloudWorkspace'
import { usePowerBIAgent } from './hooks/usePowerBIAgent'
import { useAuth } from './hooks/useAuth'
import type { BatchOperationResult } from './types'

const unavailable = async () => { throw new Error(tr('auth:organizationDataAccessIsCurrentlyUnavailable')) }
const emptyBatch = async (): Promise<BatchOperationResult> => ({succeededIds:[], failed:[]})

export function App() {
  useTranslation()
  const auth = useAuth()
  const [collapsed, setCollapsed] = useState(() =>
    typeof window.matchMedia === 'function' ? window.matchMedia('(max-width: 760px)').matches : false)
  if (auth.session?.identity_mode === 'LOCAL_DEV') return <LocalWorkspace />
  if (auth.session?.authenticated) return <CloudWorkspace key={auth.generation} session={auth.session}
    onAuthInvalid={auth.refresh} sessionCheckError={auth.sessionCheckError} collapsed={collapsed} onToggle={()=>setCollapsed(v=>!v)}
    account={{session:auth.session,state:auth.state,login:auth.login,logout:auth.logout,refresh:auth.refresh}} />
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
    <main className={`chat-main ${auth.session?.authenticated ? '' : 'auth-welcome'}`}>
      {auth.session?.authenticated ? <CloudWorkspace key={auth.generation} session={auth.session}
        onAuthInvalid={auth.refresh} /> : <>
      <h1>{auth.session?.authenticated ? tr('auth:welcomeBack') : tr('auth:askQuestionsAboutYourOrganizationsPowerBiData')}</h1>
      {auth.state === 'SESSION_ESTABLISHING' || auth.state === 'AUTHENTICATING'
        ? <p role="status">{auth.state === 'AUTHENTICATING' ? tr('auth:signingIn') : tr('auth:checkingYourSession')}</p>
        : auth.session?.authenticated ? <p>{tr('auth:youAreSignedInOrganizationDataFeaturesWillBe')}</p>
        : <p role={auth.state === 'SIGNED_OUT' ? 'status' : 'alert'}>{
          auth.logoutPending ? tr('auth:signoutIsIncompleteTryAgain') : publicText(auth.sessionCheckError) || (auth.state === 'SESSION_EXPIRED' ? tr('auth:yourSessionHasExpiredSignInAgain')
          : auth.state === 'CONSENT_REQUIRED' ? tr('auth:approvalIsRequiredSignInOrContactYourAdministrator')
          : auth.state === 'AUTH_ERROR' ? tr('auth:signinWasNotCompletedTryAgainOrContactYour') : tr('auth:signInToViewYourAccount'))}</p>}
      {auth.sessionCheckError ? <button type="button" onClick={()=>void auth.refresh()}>{tr('auth:checkSessionAgain')}</button> : null}
      {auth.logoutPending ? <button type="button" onClick={() => void auth.logout()}>{tr('auth:retrySignout')}</button> : null}
      </>}
    </main>
  </div>
}

function LocalWorkspace() {
  useTranslation()
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
            <h1>{publicText(app.title)}</h1>
          </header>
        ) : null}
        <ConversationView
          projectionContext={{mode:app.effectiveRuntimeMode,conversationId:app.activeConversationId}}
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
