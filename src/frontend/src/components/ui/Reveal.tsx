import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'

/**
 * A mount entrance: fade plus a small inline-start drift, staggered by `index` when used in lists.
 *
 * Two rules keep it honest. First, the animation lives entirely in inline styles driven by the
 * `--motion-*` tokens, so a palette or token change re-times every entrance at once. Second, it
 * fully disables itself under `prefers-reduced-motion` — checked live in JS rather than only in
 * CSS, so no one-frame flash plays before the media query applies. Content is always rendered;
 * only the entrance is conditional. Never use this to hide loading state — that is Skeleton's job.
 */
export function Reveal({
  children,
  index = 0,
  className = '',
  as: Tag = 'div',
}: {
  children: ReactNode
  /** Stagger position in a list; each step adds one --motion-instant of delay, capped at 5. */
  index?: number
  className?: string
  as?: 'div' | 'section' | 'article' | 'li'
}) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return
    }
    const frame = requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)))
    return () => cancelAnimationFrame(frame)
  }, [])

  const style: CSSProperties = visible
    ? {
        opacity: 1,
        transform: 'none',
        transitionProperty: 'opacity, transform',
        transitionDuration: 'var(--motion-base)',
        transitionTimingFunction: 'var(--motion-ease)',
        transitionDelay: `calc(var(--motion-instant) * ${Math.min(Math.max(index, 0), 5)})`,
      }
    : { opacity: 0, transform: 'translateY(6px)' }

  return (
    <Tag className={className} style={style}>
      {children}
    </Tag>
  )
}
