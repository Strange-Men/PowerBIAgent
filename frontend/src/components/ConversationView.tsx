import { useTranslation } from 'react-i18next'
import { tr } from '../i18n'
import { BarChart3 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { ConversationMessage } from '../types'
import { AssistantMessage } from './AssistantMessage'
import type { ProjectionContext } from '../hooks/usePresentation'

interface ConversationViewProps {
  projectionContext?: ProjectionContext
  welcomeDescription?: string
  messages: ConversationMessage[]
  sending: boolean
  loadingConversation: boolean
  restored: boolean
}

export function ConversationView({
  projectionContext,
  welcomeDescription = tr('chat:queryDataGenerateAReportOrStartANew'),
  messages,
  sending,
  loadingConversation,
  restored,
}: ConversationViewProps) {
  useTranslation()
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = scrollRef.current
    if (element) element.scrollTop = element.scrollHeight
  }, [messages, sending, loadingConversation])

  if (messages.length === 0 && !loadingConversation) {
    return (
      <section className="welcome" aria-labelledby="welcome-title">
        <div className="welcome-icon" aria-hidden="true">
          <BarChart3 size={29} strokeWidth={1.6} />
          <span>✦</span>
        </div>
        <h1 id="welcome-title">{tr('chat:whatWouldYouLikeToAnalyzeToday')}</h1>
        <p>{welcomeDescription}</p>
      </section>
    )
  }

  return (
    <div className="message-scroll" aria-live="polite" ref={scrollRef}>
      <div className="message-list">
        {restored ? (
          <p className="history-note">
            {tr('chat:yourSavedConversationHasBeenRestored')}</p>
        ) : null}
        {messages.map((message) =>
          message.role === 'user' ? (
            <div className="user-message-row" key={message.id}>
              <p className="user-message">{message.content}</p>
            </div>
          ) : (
            <AssistantMessage message={message} projectionContext={projectionContext} key={message.id} />
          ),
        )}
        {loadingConversation || sending ? (
          <div className="assistant-message assistant-loading" role="status" aria-label={tr('chat:analyzing')}>
            <div className="typing-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <span>{loadingConversation ? tr('chat:restoringConversation') : tr('chat:analyzingData')}</span>
          </div>
        ) : null}
      </div>
    </div>
  )
}
