import type { ReactNode } from 'react'

/**
 * The "nothing here" panel: a dashed hairline instead of a solid one, so it reads as a space waiting
 * to be filled rather than as a card that happens to be empty.
 */
export function EmptyState({
  icon,
  title,
  body,
  action,
  className = '',
}: {
  icon?: ReactNode
  title: string
  body?: string
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={`flex flex-col items-center rounded-xl border border-dashed border-line-strong bg-surface px-6 py-14 text-center ${className}`}
    >
      {icon && (
        <span className="mb-5 grid size-12 place-items-center rounded-xl bg-surface-muted text-ink-muted" aria-hidden="true">
          {icon}
        </span>
      )}

      <h2 className="text-base font-semibold text-ink">{title}</h2>
      {body && <p className="mt-2 max-w-md text-sm leading-relaxed text-ink-muted">{body}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}
