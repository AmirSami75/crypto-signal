import type { ReactNode } from 'react'
import { Card } from './Card'

/**
 * One figure, labelled.
 *
 * The shape is straight from the reference: a small grey caption, a large value under it, and an
 * optional line of context below. The value is wrapped in `.num`, which pins Latin digits and isolates
 * them bidirectionally — without that, a value like `2/3` renders as `3/2` inside Persian prose,
 * because `/` is direction-neutral and takes the paragraph's direction rather than the number's.
 *
 * `trailing` is for a badge or a status dot, and sits on the inline-end of the label row.
 */
export function StatCard({
  label,
  value,
  caption,
  trailing,
  className = '',
  tone,
  delta,
  icon,
}: {
  label: string
  value: ReactNode
  caption?: ReactNode
  trailing?: ReactNode
  className?: string
  /**
   * Optional inline-start accent bar, drawn from the tone system so it works on both palettes.
   * Decorative only — the label still carries the meaning for assistive tech.
   */
  tone?: 'neutral' | 'accent' | 'success' | 'warn' | 'danger'
  /** Optional second line under the value, e.g. a delta or a trend note. */
  delta?: ReactNode
  /** Optional icon rendered at the inline-end of the label row, before `trailing`. */
  icon?: ReactNode
}) {
  const bar: Record<NonNullable<typeof tone>, string> = {
    neutral: 'bg-line-strong',
    accent: 'bg-accent',
    success: 'bg-success',
    warn: 'bg-warn',
    danger: 'bg-danger',
  }
  return (
    <Card as="article" className={`p-5 ${className}`}>
      <div className="flex items-start gap-3">
        {tone && <span aria-hidden="true" className={`mt-0.5 w-1 shrink-0 self-stretch rounded-full ${bar[tone]}`} />}
        <p className="micro-label min-w-0 flex-1">{label}</p>
        {icon}
        {trailing}
      </div>

      <p className="num mt-3 text-2xl font-semibold text-ink">{value}</p>
      {delta && <p className="mt-1.5 text-xs leading-relaxed text-ink-soft">{delta}</p>}
      {caption && <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">{caption}</p>}
    </Card>
  )
}
