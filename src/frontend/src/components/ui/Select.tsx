import { forwardRef, type SelectHTMLAttributes } from 'react'

/**
 * A native `<select>`, wearing `Input`'s geometry.
 *
 * Native rather than a custom listbox on purpose: the platform control already has keyboard
 * navigation, type-ahead, correct assistive-technology semantics and — on a phone — the OS picker.
 * Reimplementing that to gain control of the option list's styling is a bad trade for a form with
 * four and six options in it.
 *
 * The one thing the native control gives up is the arrow, since `appearance: none` is needed to stop
 * the platform drawing its own on the wrong side. The chevron below is drawn at the field's logical
 * `end` and the gutter reserved with `pe-10`, so it mirrors with the document.
 */
const CHEVRON =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none" stroke="%238c8c8c" stroke-width="1.7" stroke-linecap="round"><path d="M5.5 8l4.5 4.5L14.5 8"/></svg>',
  )

// `size` is omitted from the native attributes before being redeclared: on a `<select>` it already
// means "how many rows are visible", so intersecting the two would resolve to `never` and make the
// prop unusable rather than merely confusing.
type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> & {
  isInvalid?: boolean
  /** `sm` matches `Button`'s small size, for a select that sits in a toolbar rather than a form. */
  size?: 'sm' | 'md'
}

const SIZES = {
  sm: { field: 'h-9 px-3 pe-9 text-[0.8125rem]', chevron: 'end-2.5 size-4' },
  md: { field: 'h-11 px-4 pe-10 text-sm', chevron: 'end-3.5 size-5' },
} as const

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { isInvalid = false, size = 'md', className = '', children, ...rest },
  ref,
) {
  const dimensions = SIZES[size]

  return (
    <div className="relative">
      <select
        ref={ref}
        aria-invalid={isInvalid || undefined}
        className={[
          'w-full appearance-none rounded-xl border bg-surface text-ink',
          dimensions.field,
          'transition-colors focus:border-accent',
          'disabled:cursor-not-allowed disabled:bg-surface-muted disabled:opacity-70',
          isInvalid ? 'border-danger focus:border-danger' : 'border-line',
          className,
        ].join(' ')}
        {...rest}
      >
        {children}
      </select>

      <span
        aria-hidden="true"
        className={`pointer-events-none absolute top-1/2 -translate-y-1/2 bg-center bg-no-repeat opacity-80 ${dimensions.chevron}`}
        style={{ backgroundImage: `url("${CHEVRON}")` }}
      />
    </div>
  )
})
