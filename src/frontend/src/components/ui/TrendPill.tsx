import type { ReactNode } from 'react'

/**
 * A small direction pill: up, down, or flat.
 *
 * Built on the same translucent-tone recipe as Badge (border/25, fill/10, -ink text) so it
 * reads on both palettes. The glyph is an arrow character, not an icon dependency — and the
 * `aria-label` carries the meaning because colour alone never does.
 */

export type TrendDirection = 'up' | 'down' | 'flat'

const TONES: Record<TrendDirection, string> = {
  up: 'border-success/25 bg-success/10 text-success-ink',
  down: 'border-danger/25 bg-danger/10 text-danger-ink',
  flat: 'border-line bg-surface-muted text-ink-muted',
}

const GLYPHS: Record<TrendDirection, string> = {
  up: '▲',
  down: '▼',
  flat: '●',
}

export function TrendPill({
  direction,
  label,
  className = '',
}: {
  direction: TrendDirection
  /** Accessible name, e.g. the Persian word for rising/falling/steady. */
  label: string
  className?: string
}) {
  return (
    <span
      role="img"
      aria-label={label}
      className={`num inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium leading-none ${TONES[direction]} ${className}`}
    >
      <span aria-hidden="true">{GLYPHS[direction]}</span>
      {label}
    </span>
  )
}
