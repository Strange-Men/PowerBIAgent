import { AlertCircle, CircleHelp, Info } from 'lucide-react'
import type { AssistantMessage as AssistantMessageModel } from '../types'
import { ReportAttachment } from './ReportAttachment'

interface AssistantMessageProps {
  message: AssistantMessageModel
}

export function AssistantMessage({ message }: AssistantMessageProps) {
  const StatusIcon =
    message.kind === 'error'
      ? AlertCircle
      : message.kind === 'clarification'
        ? CircleHelp
        : message.kind === 'unsupported'
          ? Info
          : null

  return (
    <article className={`assistant-message assistant-${message.kind}`}>
      {StatusIcon ? (
        <div className="assistant-status-icon" aria-hidden="true">
          <StatusIcon size={18} />
        </div>
      ) : null}
      <div className="assistant-content">
        <p>{message.content}</p>
        {message.report ? <ReportAttachment report={message.report} /> : null}
      </div>
    </article>
  )
}
