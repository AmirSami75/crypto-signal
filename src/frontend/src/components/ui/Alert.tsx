import type { ReactNode } from 'react'

type Tone = 'error' | 'success' | 'warn' | 'info'

const TONES: Record<Tone, string> = {
  error: 'border-danger/25 bg-danger/8 text-danger-ink',
  success: 'border-success/25 bg-success/8 text-success-ink',
  warn: 'border-warn/25 bg-warn/8 text-warn-ink',
  info: 'border-line bg-surface-muted text-ink-soft',
}

type AlertProps = {
  tone?: Tone
  title?: string
  children?: ReactNode
  /** Rendered as a bulleted list under the message — for the API's pipe-separated validation lists. */
  details?: string[]
  className?: string
}

export function Alert({ tone = 'info', title, children, details, className = '' }: AlertProps) {
  return (
    <div
      // Errors interrupt; a success confirmation waits its turn. Both need announcing — a message
      // that is only drawn is invisible to anyone who submitted the form by keyboard.
      role={tone === 'error' ? 'alert' : 'status'}
      className={`flex gap-3 rounded-xl border p-4 text-sm ${TONES[tone]} ${className}`}
    >
      <span className="mt-px shrink-0" aria-hidden="true">
        {tone === 'success' ? <CheckIcon /> : tone === 'error' ? <AlertIcon /> : <InfoIcon />}
      </span>

      <div className="min-w-0 space-y-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="leading-relaxed">{children}</div>}

        {details && details.length > 0 && (
          // ps-4 rather than pl-4: the marker indent has to sit on the right in RTL.
          <ul className="list-disc space-y-0.5 ps-4">
            {details.map((detail) => (
              <li key={detail}>{detail}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.9" className="size-4.5" aria-hidden="true">
      <circle cx="10" cy="10" r="7.6" opacity="0.35" />
      <path d="M6.4 10.3l2.5 2.4 4.7-5.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function AlertIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4.5" aria-hidden="true">
      <circle cx="10" cy="10" r="7.6" />
      <path d="M10 6.2v5" strokeLinecap="round" />
      <circle cx="10" cy="13.7" r=".95" fill="currentColor" stroke="none" />
    </svg>
  )
}

function InfoIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4.5" aria-hidden="true">
      <circle cx="10" cy="10" r="7.6" />
      <path d="M10 9.3v4.5" strokeLinecap="round" />
      <circle cx="10" cy="6.4" r=".95" fill="currentColor" stroke="none" />
    </svg>
  )
}
