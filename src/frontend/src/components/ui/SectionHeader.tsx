import type { ReactNode } from 'react'
import { Eyebrow } from './Card'

/**
 * A section heading: title, optional subtitle, optional trailing actions.
 *
 * Pages currently hand-roll this shape (a flex row with an Eyebrow and a button pushed to the far
 * side), which is how the `ms-auto` wrap bug from the scanner polish got in. One component means
 * the `justify-between` anchoring is written once and stays written.
 */
export function SectionHeader({
  title,
  subtitle,
  actions,
  className = '',
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div className={`flex flex-wrap items-center justify-between gap-3 ${className}`}>
      <div className="min-w-0">
        <Eyebrow>{title}</Eyebrow>
        {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}
