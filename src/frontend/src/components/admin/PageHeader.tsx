import type { ReactNode } from 'react'

/**
 * Title, one line of context, and the page's primary action.
 *
 * `flex-wrap` with the actions allowed to fall to their own line rather than a fixed two-column
 * layout: "کاربر جدید" next to a two-line subtitle does not fit at 375px, and a button squeezed to
 * three characters wide is worse than a button on the next row.
 */
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: string
  actions?: ReactNode
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      <div className="min-w-0">
        <h1 className="text-[1.375rem] font-semibold sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-muted">{subtitle}</p>}
      </div>

      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  )
}
