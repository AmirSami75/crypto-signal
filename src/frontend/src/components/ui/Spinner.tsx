/**
 * Loading indicator, drawn in `currentColor`.
 *
 * Inheriting the colour is what lets the same component sit inside a filled primary button, on a
 * plain card, and inside a tinted status row without a `tone` prop: the track is the same colour at
 * low opacity, so it always has contrast against whatever it is on.
 *
 * Rotation is not mirrored for RTL — a spinner is not a directional affordance, and flipping it would
 * just make it spin backwards. Contrast this with `Chevron`, which is.
 */
export function Spinner({
  size = 'md',
  className = '',
  /** Inside a button that already sets `aria-busy`, the spinner is decoration and should stay silent. */
  decorative = false,
}: {
  size?: 'sm' | 'md' | 'lg'
  className?: string
  decorative?: boolean
}) {
  const dimension = size === 'sm' ? 'size-4' : size === 'lg' ? 'size-7' : 'size-5'

  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={`${dimension} shrink-0 animate-spin ${className}`}
      role={decorative ? undefined : 'status'}
      aria-label={decorative ? undefined : 'در حال بارگذاری'}
      aria-hidden={decorative || undefined}
    >
      <circle cx="12" cy="12" r="9.25" stroke="currentColor" strokeWidth="2.25" opacity="0.22" />
      <path d="M21.25 12A9.25 9.25 0 0 0 12 2.75" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" />
    </svg>
  )
}
