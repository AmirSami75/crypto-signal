import { forwardRef, type InputHTMLAttributes } from 'react'

/**
 * 44px, 1rem radius, one hairline border — the same geometry as `Button`, so a field and the button
 * under it line up rather than nearly line up.
 *
 * No focus ring is declared here. `:focus-visible` in the base layer draws one outline for every
 * focusable thing in the product, and browsers always treat a text field as focus-visible, including
 * on a mouse click. Adding a ring as well would double it.
 */
export const inputClasses = [
  'h-11 w-full rounded-xl border bg-surface px-4 text-sm text-ink',
  'placeholder:text-ink-faint',
  'transition-colors',
  'focus:border-accent',
  'disabled:cursor-not-allowed disabled:bg-surface-muted disabled:opacity-70',
].join(' ')

type InputProps = InputHTMLAttributes<HTMLInputElement> & { isInvalid?: boolean }

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { isInvalid = false, className = '', ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={isInvalid || undefined}
      className={[inputClasses, isInvalid ? 'border-danger focus:border-danger' : 'border-line', className].join(' ')}
      {...rest}
    />
  )
})
