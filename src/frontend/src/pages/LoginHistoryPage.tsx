import { useCallback, useEffect, useMemo, useState } from 'react'
import { FilterBar } from '../components/admin/FilterBar'
import { PageHeader } from '../components/admin/PageHeader'
import { Alert } from '../components/ui/Alert'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Field } from '../components/ui/Field'
import { Input } from '../components/ui/Input'
import { Pagination } from '../components/ui/Pagination'
import { fa } from '../i18n/fa'
import { api } from '../lib/api'
import type { LoginHistoryEntry, LoginHistoryFilters } from '../lib/apiTypes'
import { ABSENT, describeClient, hasValue } from '../lib/format'
import { useDebounced } from '../lib/useDebounced'
import { useResource } from '../lib/useResource'

/**
 * Sign-in attempts, newest first.
 *
 * **This is every user's history, not the reader's own** — `LoginHistoryController.Get` builds a
 * self-scoping filter and then discards it (`BaseQuery.Where(…)` as a bare statement, and LINQ is
 * lazy and non-mutating), so the endpoint answers with the whole table. The banner says so rather
 * than letting a reader assume these four rows are their own last four sign-ins.
 *
 * The IP filter is the only one the search DTO offers, so it is the only one here. `dateTime` is a
 * full Jalali timestamp — the one audit-ish field the server sends *without* an actor name glued to
 * it — so it renders directly instead of through `jalaliDate`.
 */

export function LoginHistoryPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [ip, setIp] = useState('')

  const debouncedIp = useDebounced(ip)

  const filters = useMemo<LoginHistoryFilters>(() => ({ IP: debouncedIp.trim() || undefined }), [debouncedIp])

  const isFiltered = ip !== ''

  const history = useResource(
    useCallback(
      (signal: AbortSignal) => api.loginHistory.paged({ page, pageSize }, filters, signal),
      [page, pageSize, filters],
    ),
  )

  useEffect(() => {
    setPage(1)
  }, [filters, pageSize])

  const columns = useMemo<Column<LoginHistoryEntry>[]>(
    () => [
      {
        key: 'dateTime',
        header: fa.loginHistory.colDateTime,
        className: 'whitespace-nowrap',
        cell: (entry) => <span className="num text-ink">{entry.dateTime}</span>,
      },
      {
        key: 'status',
        header: fa.loginHistory.colStatus,
        cell: (entry) => (
          <Badge tone={entry.status === 'Success' ? 'success' : 'danger'}>
            {entry.status === 'Success' ? fa.loginHistory.statusSuccess : fa.loginHistory.statusError}
          </Badge>
        ),
      },
      {
        key: 'ip',
        header: fa.loginHistory.colIp,
        className: 'whitespace-nowrap',
        cell: (entry) =>
          hasValue(entry.ip) ? (
            <span className="num text-ink-soft">{entry.ip}</span>
          ) : (
            <span className="text-ink-muted">{ABSENT}</span>
          ),
      },
      {
        key: 'client',
        header: fa.loginHistory.colClient,
        cell: (entry) => {
          const client = describeClient(entry.userAgent)
          return client === ABSENT ? (
            <span className="text-ink-muted">{ABSENT}</span>
          ) : (
            <span className="latin text-ink-soft">{client}</span>
          )
        },
      },
    ],
    [],
  )

  return (
    <div className="space-y-5">
      <PageHeader title={fa.loginHistory.title} subtitle={fa.loginHistory.subtitle} />

      <Alert tone="info">{fa.loginHistory.scopeNote}</Alert>

      <FilterBar isFiltered={isFiltered} onClear={() => setIp('')}>
        <Field label={fa.loginHistory.filterIp}>
          {({ inputId }) => (
            <Input
              id={inputId}
              value={ip}
              onChange={(event) => setIp(event.target.value)}
              autoComplete="off"
              inputMode="numeric"
              dir="ltr"
              className="num text-start"
            />
          )}
        </Field>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={history.data?.items ?? []}
        rowKey={(entry) => entry.id}
        isLoading={history.isLoading}
        isRefreshing={history.isRefreshing}
        error={history.error}
        emptyTitle={fa.loginHistory.emptyTitle}
        emptyBody={fa.loginHistory.emptyBody}
        skeletonRows={Math.min(pageSize, 8)}
        emptyAction={
          isFiltered ? (
            <Button variant="outline" size="sm" onClick={() => setIp('')}>
              {fa.table.clearFilters}
            </Button>
          ) : undefined
        }
      />

      <Pagination
        page={page}
        pageSize={pageSize}
        totalRecords={history.data?.totalRecords ?? 0}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
        isBusy={history.isLoading || history.isRefreshing}
      />
    </div>
  )
}
