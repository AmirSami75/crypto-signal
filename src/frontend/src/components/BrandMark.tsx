/**
 * The brand mark: a filled square with a rising-line glyph.
 *
 * A solid fill rather than the tinted-ring treatment the rest of the interface uses, because this is
 * the one place the accent is allowed to be loud — it is an identity, not a status. `--accent-fill`
 * and `--accent-on` are a contrast-checked pair in both palettes, so the glyph stays legible when the
 * theme flips.
 *
 * Inline SVG rather than a file so it needs no extra request and scales with `className`.
 */
export function BrandMark({ className = '' }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`grid size-8 shrink-0 place-items-center rounded-lg bg-accent-fill text-accent-on ${className}`}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" className="size-[62%]">
        <path d="M3.5 16.5l4.5-5 3.5 3 4-6.5 3 4.5 2-2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  )
}
