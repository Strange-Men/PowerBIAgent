import { AlertCircle, CircleHelp, Info } from 'lucide-react'
import type { AssistantMessage as AssistantMessageModel } from '../types'
import { ReportAttachment } from './ReportAttachment'
import { StructuredBlocks } from './StructuredBlocks'
import { usePresentation, type ProjectionContext } from '../hooks/usePresentation'
import { tr, publicText } from '../i18n'

interface AssistantMessageProps {
  message: AssistantMessageModel
  projectionContext?: ProjectionContext
}

export function AssistantMessage({ message, projectionContext }: AssistantMessageProps) {
  const projection=usePresentation(message,projectionContext)
  const displayed=projection.value ? {...message,content:projection.value.answer,presentation:projection.value.presentation} : message
  const waiting=projection.pending
  const unavailable=projection.failed || (message.restored && !message.presentationAvailable && projection.locale==='en-US')
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
        {waiting ? <p role="status">{tr('resources:loading')}</p> : unavailable ? <p>{tr('chat:projectionUnavailable')}</p> : displayed.presentation ? (
          <StructuredBlocks
            presentation={displayed.presentation}
            fallbackText={displayed.content}
            report={message.report}
          />
        ) : (
          <p>{publicText(displayed.content)}</p>
        )}
        {message.report && !message.presentation ? (
          <ReportAttachment report={message.report} />
        ) : null}
      </div>
    </article>
  )
}
