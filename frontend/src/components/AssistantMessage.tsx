import { AlertCircle, CircleHelp, Info } from 'lucide-react'
import type { AssistantMessage as AssistantMessageModel } from '../types'
import { ReportAttachment } from './ReportAttachment'
import { StructuredBlocks } from './StructuredBlocks'

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
  const liveRegion =
    message.kind === 'error'
      ? { role: 'alert', 'aria-live': 'assertive' as const }
      : message.kind === 'clarification' || message.kind === 'unsupported'
        ? { role: 'status', 'aria-live': 'polite' as const }
        : {}

  return (
    <article
      className={`assistant-message assistant-${message.kind}`}
      {...liveRegion}
    >
      {StatusIcon ? (
        <div className="assistant-status-icon" aria-hidden="true">
          <StatusIcon size={18} />
        </div>
      ) : null}
      <div className="assistant-content">
        {message.presentation ? (
          <StructuredBlocks
            presentation={message.presentation}
            fallbackText={message.content}
            report={message.report}
          />
        ) : (
          <p>{message.content}</p>
        )}
        {message.report && !message.presentation ? (
          <ReportAttachment report={message.report} />
        ) : null}
      </div>
    </article>
  )
}
