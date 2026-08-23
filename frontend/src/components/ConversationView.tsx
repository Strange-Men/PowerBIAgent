import { BarChart3 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { ConversationMessage } from '../types'
import { AssistantMessage } from './AssistantMessage'

interface ConversationViewProps {
  messages: ConversationMessage[]
  sending: boolean
  loadingConversation: boolean
  restored: boolean
}

export function ConversationView({
  messages,
  sending,
  loadingConversation,
  restored,
}: ConversationViewProps) {
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
        <h1 id="welcome-title">今天想分析什么数据？</h1>
        <p>可以查询数据、生成报表或开始新的分析。</p>
      </section>
    )
  }

  return (
    <div className="message-scroll" aria-live="polite" ref={scrollRef}>
      <div className="message-list">
        {restored ? (
          <p className="history-note">
            已恢复保存的历史对话。
          </p>
        ) : null}
        {messages.map((message) =>
          message.role === 'user' ? (
            <div className="user-message-row" key={message.id}>
              <p className="user-message">{message.content}</p>
            </div>
          ) : (
            <AssistantMessage message={message} key={message.id} />
          ),
        )}
        {loadingConversation || sending ? (
          <div className="assistant-message assistant-loading" role="status" aria-label="正在分析">
            <div className="typing-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <span>{loadingConversation ? '正在恢复对话' : '正在分析数据'}</span>
          </div>
        ) : null}
      </div>
    </div>
  )
}
