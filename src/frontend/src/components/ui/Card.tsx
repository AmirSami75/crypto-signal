import type { ReactNode } from 'react'

/**
 * A panel, and the reason the interface has no shadows.
 *
 * Depth in this design comes from a single hairline and the space around it. On the light palette the
 * card and the page are both white, so the border *is* the card — which is why `border-line` is not
 * optional and why there is no elevation prop. Things that genuinely float (a popover, the mobile
 * drawer) reach for `shadow-float` directly; a card is not one of them.
 */

type CardProps = {
  children: ReactNode
  className?: string
  /** Filled with the muted surface instead of the card surface, for a panel inside a panel. */
  muted?: boolean
  as?: 'div' | 'article' | 'section' | 'li'
}

export function Card({ children, className = '', muted = false, as: Tag = 'div' }: CardProps) {
  return (
    <Tag
      className={[
        'rounded-xl',
        muted ? 'border border-transparent bg-surface-muted' : 'border border-line bg-surface',
        className,
      ].join(' ')}
    >
      {children}
    </Tag>
  )
}

/**
 * The small wide-tracked caption above a heading or a value.
 *
 * Grey, not accent-coloured: with a hairline-and-whitespace design the accent has to stay scarce or it
 * stops meaning anything. Persian has no capital letters, so the tracking and weight do the work that
 * `uppercase` does in the Latin original.
 */
export function Eyebrow({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <p className={`micro-label ${className}`}>{children}</p>
}
