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
  // A soft vertical bloom rather than a hard bar: the tone should read as light coming off the card
  // edge, not as a coloured stripe glued to it.
  const bar: Record<NonNullable<typeof tone>, string> = {
    neutral: 'bg-gradient-to-b from-line-strong to-transparent',
    accent: 'bg-gradient-to-b from-accent to-transparent',
    success: 'bg-gradient-to-b from-success to-transparent',
    warn: 'bg-gradient-to-b from-warn to-transparent',
    danger: 'bg-gradient-to-b from-danger to-transparent',
  }
  return (
    <Card as="article" className={`group p-5 transition-colors hover:border-line-strong ${className}`}>
      <div className="flex items-start gap-3">
        {tone && <span aria-hidden="true" className={`mt-0.5 w-1 shrink-0 self-stretch rounded-full ${bar[tone]}`} />}
        <p className="micro-label min-w-0 flex-1">{label}</p>
        {icon}
        {trailing}
      </div>

      <p className="stat-value mt-3 text-[1.75rem] font-semibold text-ink">{value}</p>
      {delta && <p className="mt-1.5 text-xs leading-relaxed text-ink-soft">{delta}</p>}
      {caption && <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">{caption}</p>}
    </Card>
  )
}
