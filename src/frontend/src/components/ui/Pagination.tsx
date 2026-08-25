import { useEffect } from 'react'
import { fa } from '../../i18n/fa'
import { pageRange } from '../../lib/format'
import { IconButton } from './IconButton'
import { Select } from './Select'

/**
 * Page controls for the admin listings.
 *
 * Two details here are RTL-specific and both are easy to get backwards.
 *
 * **The chevrons are mirrored, on purpose.** Everything else in this design mirrors by itself through
 * logical properties, but a glyph is not a layout property — an arrow drawn pointing left keeps
 * pointing left however the page flips. In Persian, reading runs right-to-left, so *previous* is
 * toward the right and *next* is toward the left: the opposite of the LTR original. The two icons
 * below are therefore swapped relative to what their names suggest, which is why they are named for
 * the direction they point rather than the action they perform.
 *
 * **The page numbers carry `.num`.** A bare numeral inside RTL text is direction-neutral, so
 * `"۳ / ۱۰"`-style punctuation migrates to the wrong side of the digits. The class isolates the run.
 *
 * Numbered page buttons are deliberately absent. With 62 login-history rows the window is trivial; at
 * a few thousand it is a strip of twenty buttons nobody aims at. Previous/next plus a stated position
 * is what an operator actually uses, and the page-size selector covers "show me more at once".
 *
 * **Self-healing against stale pages.** Filters and page-size changes shrink the result set under a
 * cursor that used to be valid: land on "page 3 of 12", filter, and a naive control leaves you on
 * page 3 with both arrows dead and an empty table. This component owns the recovery instead of
 * trusting every caller to reset — when `page` falls outside `1..lastPage` it calls back with the
 * corrected value in an effect (never during render), so the indicator always names a real page and
 * exactly one arrow is enabled whenever another page exists. When everything fits one page there is
 * nothing to page through, and the whole prev/next strip stays out of the DOM rather than presenting
 * two permanently disabled buttons as broken controls.
 */

const PAGE_SIZES = [10, 25, 50, 100]

export function Pagination({
  page,
  pageSize,
  totalRecords,
  onPageChange,
  onPageSizeChange,
  isBusy = false,
}: {
  page: number
  pageSize: number
  totalRecords: number
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
  isBusy?: boolean
}) {
  const lastPage = Math.max(1, Math.ceil(totalRecords / pageSize))
  const [from, to] = pageRange(page, pageSize, totalRecords)
  const hasMultiplePages = lastPage > 1

  // Recover from a stale cursor after the data shrinks. An effect, not a render-time clamp: setting
  // state during render re-renders before commit, and the parent owns `page`.
  useEffect(() => {
    if (page > lastPage) onPageChange(lastPage)
  }, [page, lastPage, onPageChange])

  const handlePageSizeChange = (nextSize: number) => {
    // The visible rows move under a page-size change; page N of the old size is not page N of the
    // new one. Restarting at 1 is the only answer that is never empty by construction.
    onPageSizeChange(nextSize)
    if (page !== 1) onPageChange(1)
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-2 text-xs text-ink-muted">
        <span>{fa.table.rowsPerPage}</span>
        <Select
          value={pageSize}
          onChange={(event) => handlePageSizeChange(Number(event.target.value))}
          disabled={isBusy}
          size="sm"
          className="w-20"
          aria-label={fa.table.rowsPerPage}
        >
          {PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </Select>
      </div>

      <div className="flex items-center gap-3">
        <p className="text-xs text-ink-muted">
          {totalRecords === 0 ? (
            fa.table.noRecords
          ) : (
            <>
              <span className="num">{from}</span>
              {fa.table.rangeSeparator}
              <span className="num">{to}</span>
              {fa.table.rangeOf}
              <span className="num">{totalRecords}</span>
            </>
          )}
        </p>

        {hasMultiplePages && (
          <div className="flex items-center gap-1">
            <IconButton
              label={fa.table.previousPage}
              disabled={page <= 1 || isBusy}
              onClick={() => onPageChange(page - 1)}
            >
              <PreviousIcon />
            </IconButton>

            <p className="min-w-16 text-center text-xs text-ink-soft">
              <span className="num">{page}</span>
              <span className="mx-1 text-ink-faint">/</span>
              <span className="num">{lastPage}</span>
            </p>

            <IconButton
              label={fa.table.nextPage}
              disabled={page >= lastPage || isBusy}
              onClick={() => onPageChange(page + 1)}
            >
              <NextIcon />
            </IconButton>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * *Previous*, drawn pointing toward the start of the reading order — which in Persian is the right.
 *
 * The path is the one an LTR design would use for "next". That inversion is the whole point, and it is
 * hard-coded rather than mirrored with a transform because this interface has exactly one direction.
 */
function PreviousIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4" aria-hidden="true">
      <path d="M8 5l5 5-5 5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** *Next*, pointing the way the text flows — leftward. */
function NextIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4" aria-hidden="true">
      <path d="M12 5l-5 5 5 5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
