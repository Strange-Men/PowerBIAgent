import { useState } from 'react'
import { Composer } from './components/Composer'
import { ConversationView } from './components/ConversationView'
import { Sidebar } from './components/Sidebar'
import { usePowerBIAgent } from './hooks/usePowerBIAgent'

export function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const app = usePowerBIAgent()

  return (
    <div className="app-shell">
      <Sidebar
        collapsed={sidebarCollapsed}
        activeConversationId={app.activeConversationId}
        conversations={app.recentConversations}
        reports={app.recentReports}
        error={app.sidebarError}
        onToggle={() => setSidebarCollapsed((collapsed) => !collapsed)}
        onNewChat={app.startNewChat}
        onOpenConversation={(conversation) => void app.openConversation(conversation)}
        onSearch={app.search}
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
          reportTemplate={app.selectedReportTemplate}
          onSemanticModelChange={app.setSelectedSemanticModel}
          onReportTemplateChange={app.setSelectedReportTemplate}
          onSend={app.submitMessage}
        />
      </main>
    </div>
  )
}
