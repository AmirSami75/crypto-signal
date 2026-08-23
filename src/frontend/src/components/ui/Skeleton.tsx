/**
 * Placeholder block for content that is still in flight.
 *
 * Sized by the caller, because a skeleton that does not match the shape of what replaces it causes
 * the layout to jump — which is the one thing a skeleton exists to prevent.
 */
export function Skeleton({ className = '' }: { className?: string }) {
  return <span aria-hidden="true" className={`block animate-pulse rounded-lg bg-surface-muted ${className}`} />
}
