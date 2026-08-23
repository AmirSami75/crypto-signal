import type { ButtonHTMLAttributes } from 'react'

/**
 * Square, quiet, icon-only. Its `label` is mandatory and becomes the accessible name — an icon-only
 * control without one is an unnamed button, which is the single most common accessibility defect in a
 * dashboard header.
 */
export function IconButton({
  label,
  children,
  className = '',
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type={rest.type ?? 'button'}
      aria-label={label}
      title={label}
      className={[
        'grid size-9 shrink-0 place-items-center rounded-xl text-ink-muted',
        'transition-colors hover:bg-surface-muted hover:text-ink',
        'disabled:cursor-not-allowed disabled:opacity-55',
        className,
      ].join(' ')}
      {...rest}
    >
      {children}
    </button>
  )
}
