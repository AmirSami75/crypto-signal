import type { ReactNode } from 'react'

/**
 * A pill: hairline border, tinted ground, colour-matched text.
 *
 * Every tone is built from the same token at three strengths — `/25` for the border, `/10` for the
 * fill, and the `-ink` variant for the text. That is what makes one definition work on both palettes:
 * the tint is translucent, so it takes the card's colour underneath it, and the `-ink` token is
 * already the readable version of the hue for the current theme.
 */

type Tone = 'neutral' | 'accent' | 'success' | 'warn' | 'danger'

const TONES: Record<Tone, string> = {
  neutral: 'border-line bg-surface-muted text-ink-soft',
  accent: 'border-accent/25 bg-accent/10 text-accent-ink',
  success: 'border-success/25 bg-success/10 text-success-ink',
  warn: 'border-warn/25 bg-warn/10 text-warn-ink',
  danger: 'border-danger/25 bg-danger/10 text-danger-ink',
}

export function Badge({
  tone = 'neutral',
  children,
  className = '',
}: {
  tone?: Tone
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium leading-none ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  )
}

const DOT_TONES: Record<Tone, string> = {
  neutral: 'bg-ink-faint',
  accent: 'bg-accent',
  success: 'bg-success',
  warn: 'bg-warn',
  danger: 'bg-danger',
}

/**
 * Status dot. `pulse` marks a state still being determined rather than a settled one.
 *
 * No glow. A dot with a coloured halo is a dark-theme flourish that turns muddy on white, and the
 * halo would have to be a third token to work on both.
 */
export function StatusDot({ tone = 'neutral', pulse = false }: { tone?: Tone; pulse?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`size-2 shrink-0 rounded-full ${DOT_TONES[tone]} ${pulse ? 'animate-pulse' : ''}`}
    />
  )
}
