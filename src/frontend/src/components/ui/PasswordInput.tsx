import { forwardRef, useState, type InputHTMLAttributes } from 'react'
import { fa } from '../../i18n/fa'
import { inputClasses } from './Input'

type PasswordInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & { isInvalid?: boolean }

/**
 * Password field with a reveal toggle.
 *
 * The field is forced to `dir="ltr"` with `text-start`: passwords here must contain Latin characters
 * and digits by policy, and typing them into an RTL field puts the caret and any trailing punctuation
 * on the wrong side, which makes a correctly-typed password look mistyped.
 *
 * That one attribute is why the gutter is `ps-12` rather than `pe-12`, and it is the trap this
 * component exists to document: the two elements resolve their logical properties against *different*
 * directions. The button is positioned against the wrapper, which inherits the page's RTL, so
 * `end-1.5` puts it on the left; the padding is on the field, which is LTR, so `pe-*` would reserve
 * the right. Written that way the field holds 48px of empty space on one side and lets the placeholder
 * run under the button on the other. Both have to name the same physical side, and convention decides
 * which: an eye on the left is what Persian login forms do, so the field reserves its *start*.
 *
 * The caret stays clear of it — an LTR field fills rightward from that padded start, away from the
 * button, so typed text never reaches it.
 */
export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(function PasswordInput(
  { isInvalid = false, className = '', ...rest },
  ref,
) {
  const [isRevealed, setIsRevealed] = useState(false)

  return (
    <div className="relative">
      <input
        ref={ref}
        type={isRevealed ? 'text' : 'password'}
        dir="ltr"
        aria-invalid={isInvalid || undefined}
        className={[
          inputClasses,
          'ps-12 text-start',
          isInvalid ? 'border-danger focus:border-danger' : 'border-line',
          className,
        ].join(' ')}
        {...rest}
      />

      <button
        type="button"
        onClick={() => setIsRevealed((current) => !current)}
        // The label says what the button will do, not what the field currently is — the two read
        // oppositely and mixing them up is the usual bug here.
        aria-label={isRevealed ? fa.common.hidePassword : fa.common.showPassword}
        aria-pressed={isRevealed}
        className="absolute end-1.5 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-lg text-ink-faint transition-colors hover:bg-surface-muted hover:text-ink-soft"
      >
        {isRevealed ? <EyeOffIcon /> : <EyeIcon />}
      </button>
    </div>
  )
})

function EyeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="size-4.5" aria-hidden="true">
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12S18 18.5 12 18.5 2.5 12 2.5 12Z" strokeLinecap="round" />
      <circle cx="12" cy="12" r="3.2" />
    </svg>
  )
}

function EyeOffIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="size-4.5" aria-hidden="true">
      <path d="M4 4l16 16" strokeLinecap="round" />
      <path d="M9.9 5.8A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-2.7 3.6" strokeLinecap="round" />
      <path d="M6.4 7.7A17 17 0 0 0 2.5 12S6 18.5 12 18.5c1.2 0 2.3-.2 3.3-.6" strokeLinecap="round" />
      <path d="M9.8 10a3.2 3.2 0 0 0 4.3 4.4" strokeLinecap="round" />
    </svg>
  )
}
