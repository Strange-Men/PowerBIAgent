import { useEffect, useState } from 'react'
import { Composer } from './components/Composer'
import { ConversationView } from './components/ConversationView'
import { Sidebar } from './components/Sidebar'
import { usePowerBIAgent } from './hooks/usePowerBIAgent'

export function App() {
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
          onSemanticModelChange={app.setSelectedSemanticModel}
          onRefreshSemanticModels={app.refreshSemanticModels}
          onReportTemplateChange={app.setSelectedReportTemplate}
          onSend={app.submitMessage}
        />
      </main>
    </div>
  )
}
