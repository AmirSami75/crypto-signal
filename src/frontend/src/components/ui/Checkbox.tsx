import { useId, type ReactNode } from 'react'

/**
 * Checkbox with its label, as one clickable row.
 *
 * The native input is kept and styled rather than hidden behind a `<div>`: `accent-color` gets the
 * check mark drawn in the brand hue for free, and the real control keeps the space bar, the
 * indeterminate state, and the `:checked` semantics assistive technology reads. What it costs is
 * control over the tick's exact shape, which is not worth a reimplementation.
 *
 * The whole row is the label element, so the text is part of the hit target — a 16px box is a hard
 * target on a phone, and a permission picker is dozens of them in a column.
 */
export function Checkbox({
  checked,
  onChange,
  label,
  description,
  disabled = false,
  className = '',
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: ReactNode
  description?: ReactNode
  disabled?: boolean
  className?: string
}) {
  const id = useId()

  return (
    <label
      htmlFor={id}
      className={[
        'flex cursor-pointer items-start gap-3 rounded-xl px-3 py-2.5 transition-colors',
        disabled ? 'cursor-not-allowed opacity-55' : 'hover:bg-surface-muted',
        className,
      ].join(' ')}
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        // `mt-0.5` rather than centring: with a two-line label the box should sit on the first line,
        // not float in the middle of the block.
        className="mt-0.5 size-4 shrink-0 cursor-pointer rounded border-line accent-accent-fill disabled:cursor-not-allowed"
      />

      <span className="min-w-0 flex-1">
        <span className="block text-sm text-ink">{label}</span>
        {description && <span className="mt-0.5 block text-xs text-ink-muted">{description}</span>}
      </span>
    </label>
  )
}
