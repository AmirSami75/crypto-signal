import type { ReactNode } from 'react'
import { fa } from '../../i18n/fa'
import { Button } from '../ui/Button'

/**
 * The filter row above a listing.
 *
 * A `<section>` with an accessible name rather than a bare div, because it is a landmark a keyboard
 * user tabs past on the way to the table and "فیلترها" is what tells them what they just skipped.
 *
 * The clear button appears only when something is actually set. A permanently visible, permanently
 * disabled control adds a word of chrome to every screen in exchange for nothing — and its presence
 * when enabled is itself the signal that the table is showing a subset.
 */
export function FilterBar({
  children,
  isFiltered,
  onClear,
}: {
  /** The fields. Laid out in a responsive grid, so pass them as siblings, not pre-wrapped. */
  children: ReactNode
  isFiltered: boolean
  onClear: () => void
}) {
  return (
    <section aria-label={fa.table.filters} className="space-y-3 rounded-xl border border-line bg-surface p-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{children}</div>

      {isFiltered && (
        <div className="flex justify-end">
          <Button variant="ghost" size="sm" onClick={onClear}>
            {fa.table.clearFilters}
          </Button>
        </div>
      )}
    </section>
  )
}
