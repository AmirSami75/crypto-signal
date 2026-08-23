import { useId, type ReactNode } from 'react'

type FieldProps = {
  label: string
  /** Rendered under the control, in red, and wired to the input via aria-describedby. */
  error?: string | null
  hint?: string
  required?: boolean
  /** Receives the ids to hang on the control so the label and messages actually associate with it. */
  children: (ids: { inputId: string; describedBy: string | undefined; isInvalid: boolean }) => ReactNode
}

/**
 * Label + control + message, with the accessibility wiring done once.
 *
 * The render-prop shape exists because the ids have to reach the *control*, not a wrapper: a label
 * whose `htmlFor` points at nothing, and an error message no assistive technology can find, are the
 * two mistakes this makes impossible to repeat per-form.
 */
export function Field({ label, error, hint, required = false, children }: FieldProps) {
  const inputId = useId()
  const errorId = `${inputId}-error`
  const hintId = `${inputId}-hint`

  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') || undefined

  return (
    <div className="space-y-2">
      <label htmlFor={inputId} className="block text-[0.8125rem] font-medium text-ink-soft">
        {label}
        {required && (
          <span className="ms-1 text-danger" aria-hidden="true">
            *
          </span>
        )}
      </label>

      {children({ inputId, describedBy, isInvalid: Boolean(error) })}

      {hint && !error && (
        <p id={hintId} className="text-xs text-ink-muted">
          {hint}
        </p>
      )}

      {error && (
        // aria-live so a message that appears after a failed submit is announced, not just drawn.
        <p id={errorId} role="alert" className="text-xs text-danger-ink">
          {error}
        </p>
      )}
    </div>
  )
}
