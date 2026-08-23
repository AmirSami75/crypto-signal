import type { ButtonHTMLAttributes } from 'react'
import { Spinner } from './Spinner'

/**
 * The one control the whole product is measured by: 44px tall, 1rem radius, medium weight, colour
 * from a filled token — no gradient, no shadow, no border on the primary.
 *
 * `primary` fills with `--accent-fill` rather than the brand hue. They are the same colour deepened:
 * the brand blue behind white text is 2.7:1, which is unreadable at label size, and 4.6:1 is the same
 * blue that passes. In dark mode the relationship inverts — the bright hue becomes the fill and
 * carries near-black ink — and both cases are expressed by the two tokens rather than by a variant.
 */

type Variant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent-fill text-accent-on hover:bg-accent-fill-hover disabled:hover:bg-accent-fill',
  secondary:
    'bg-surface-muted text-accent-ink hover:bg-line/70 disabled:hover:bg-surface-muted',
  outline:
    'border border-line bg-surface text-ink hover:border-line-strong hover:bg-surface-muted disabled:hover:border-line disabled:hover:bg-surface',
  ghost: 'text-ink-soft hover:bg-surface-muted hover:text-ink disabled:hover:bg-transparent',
  // Soft rather than filled, in both themes: a filled red needs a different foreground in light and
  // dark, and a destructive action reads clearly enough as a tinted outline.
  danger:
    'border border-danger/30 bg-danger/8 text-danger-ink hover:border-danger/55 hover:bg-danger/12 disabled:hover:border-danger/30 disabled:hover:bg-danger/8',
}

const SIZES: Record<Size, string> = {
  sm: 'h-9 gap-1.5 px-3.5 text-[0.8125rem]',
  md: 'h-11 gap-2 px-5 text-sm',
  lg: 'h-12 gap-2 px-6 text-[0.9375rem]',
}

const BASE = [
  'inline-flex shrink-0 items-center justify-center rounded-xl font-medium',
  'transition-colors select-none',
  'disabled:cursor-not-allowed disabled:opacity-55',
].join(' ')

/**
 * The button's class list on its own, for the cases where the thing being styled is a *link*.
 *
 * A navigation belongs in an anchor: rendering it as a button loses middle-click, "open in new tab"
 * and the right role for assistive technology. Exporting the classes is what lets a `Link` look
 * identical without either duplicating the token list or faking a button.
 */
export function buttonClasses(
  options: { variant?: Variant; size?: Size; fullWidth?: boolean; className?: string } = {},
): string {
  const { variant = 'primary', size = 'md', fullWidth = false, className = '' } = options
  return [BASE, VARIANTS[variant], SIZES[size], fullWidth ? 'w-full' : '', className]
    .filter(Boolean)
    .join(' ')
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: Size
  /** Shows a spinner and disables the button. Use for a submit that is in flight. */
  isLoading?: boolean
  fullWidth?: boolean
}

export function Button({
  variant = 'primary',
  size = 'md',
  isLoading = false,
  fullWidth = false,
  className = '',
  disabled,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      // A button inside a form defaults to type="submit", which turns any stray button into an
      // accidental submit. Callers that want a submit say so.
      type={rest.type ?? 'button'}
      disabled={disabled || isLoading}
      // aria-busy rather than swapping the label: a screen reader should not lose the button's name
      // just because it is working.
      aria-busy={isLoading || undefined}
      className={buttonClasses({ variant, size, fullWidth, className })}
      {...rest}
    >
      {isLoading && <Spinner size="sm" decorative />}
      {children}
    </button>
  )
}
