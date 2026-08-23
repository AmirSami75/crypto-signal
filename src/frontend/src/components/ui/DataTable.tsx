import type { ReactNode } from 'react'
import { Alert } from './Alert'
import { EmptyState } from './EmptyState'
import { Skeleton } from './Skeleton'

/**
 * The table every admin listing renders through.
 *
 * One component rather than markup per page, because the states are where tables go wrong and there
 * are five of them: first load, loaded, reloading with rows still up, empty, and failed. Written by
 * hand each time, some page always ends up with a blank panel for one of them.
 *
 * **The horizontal scroll is deliberate and it is scoped.** Six columns do not fit in 375px, and the
 * alternatives are worse: dropping columns hides data the operator came for, and letting the *page*
 * scroll sideways breaks the whole layout — the sidebar detaches, the header slides, and every
 * position: sticky in the chrome stops working. So the scroll lives on the wrapper around the table
 * and nowhere else. The `min-w-0` chain from `<main>` down to here is what makes that possible; a
 * single `w-full` on an intermediate flex child would let the table push the page wide instead.
 */

export type Column<T> = {
  /** Stable identity for the React key. Not necessarily a field name. */
  key: string
  header: ReactNode
  cell: (row: T) => ReactNode
  /** `end` for a trailing actions column; the default `start` is right-aligned under `dir="rtl"`. */
  align?: 'start' | 'end'
  /** Extra classes on both the `th` and every `td` — widths, `whitespace-nowrap`, and so on. */
  className?: string
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  isLoading = false,
  isRefreshing = false,
  error = null,
  emptyTitle,
  emptyBody,
  emptyAction,
  /** Rows of skeletons on first load — matched to the page size so the panel does not resize twice. */
  skeletonRows = 6,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  isLoading?: boolean
  isRefreshing?: boolean
  error?: string | null
  emptyTitle: string
  emptyBody?: string
  emptyAction?: ReactNode
  skeletonRows?: number
}) {
  // An error with rows behind it annotates them instead of replacing them — see `useResource`, which
  // keeps the previous page on a failed refetch precisely so this branch has something to show.
  if (error && rows.length === 0 && !isLoading) return <Alert tone="error">{error}</Alert>

  if (!isLoading && rows.length === 0)
    return <EmptyState title={emptyTitle} body={emptyBody} action={emptyAction} icon={<TableIcon />} />

  const cellPadding = 'px-4 py-3'

  return (
    <div className="space-y-3">
      {error && <Alert tone="error">{error}</Alert>}

      <div className="overflow-hidden rounded-xl border border-line bg-surface">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[44rem] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line bg-surface-muted/60">
                {columns.map((column) => (
                  <th
                    key={column.key}
                    scope="col"
                    className={[
                      cellPadding,
                      'micro-label whitespace-nowrap',
                      column.align === 'end' ? 'text-end' : 'text-start',
                      column.className ?? '',
                    ].join(' ')}
                  >
                    {column.header}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody
              // Dimmed rather than emptied while a refetch is in flight: replacing rows with skeletons
              // on every filter keystroke changes the row heights and throws the reader's eye off.
              className={isRefreshing ? 'opacity-55 transition-opacity' : 'transition-opacity'}
              aria-busy={isRefreshing || undefined}
            >
              {isLoading
                ? Array.from({ length: skeletonRows }, (_, index) => (
                    <tr key={`skeleton-${index}`} className="border-b border-line last:border-b-0">
                      {columns.map((column) => (
                        <td key={column.key} className={cellPadding}>
                          <Skeleton className="h-4 w-full max-w-[10rem]" />
                        </td>
                      ))}
                    </tr>
                  ))
                : rows.map((row) => (
                    <tr
                      key={rowKey(row)}
                      className="border-b border-line transition-colors last:border-b-0 hover:bg-surface-muted/50"
                    >
                      {columns.map((column) => (
                        <td
                          key={column.key}
                          className={[
                            cellPadding,
                            'align-middle',
                            column.align === 'end' ? 'text-end' : 'text-start',
                            column.className ?? '',
                          ].join(' ')}
                        >
                          {column.cell(row)}
                        </td>
                      ))}
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function TableIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="size-6" aria-hidden="true">
      <rect x="3.5" y="5" width="17" height="14" rx="2.5" />
      <path d="M3.5 10h17M9.5 10v9" strokeLinecap="round" />
    </svg>
  )
}
