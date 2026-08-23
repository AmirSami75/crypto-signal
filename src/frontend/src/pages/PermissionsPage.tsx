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
import type { Permission, TitleFilter } from '../lib/apiTypes'
import { permissionGroupTitle, permissionResource } from '../lib/permissionGroups'
import { AuditCell } from '../components/admin/AuditCell'
import { useDebounced } from '../lib/useDebounced'
import { useResource } from '../lib/useResource'

/**
 * The permission catalogue — read-only, because the server owns it.
 *
 * `PermissionSeeder` walks every controller action carrying a `[Permission]` attribute and writes the
 * rows on startup; there is no create, update or delete endpoint, and inventing local ones would
 * produce rows no `[CustomAuthorize]` check would ever consult. So this page has no primary action and
 * says why in a banner rather than leaving the reader to wonder where the button went.
 *
 * What it *is* for is looking up what a permission name means before assigning it on the roles screen —
 * hence the group column, which reuses the same grouping the role picker sections by.
 */

export function PermissionsPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [title, setTitle] = useState('')

  const debouncedTitle = useDebounced(title)

  const filters = useMemo<TitleFilter>(() => ({ Title: debouncedTitle.trim() || undefined }), [debouncedTitle])

  const isFiltered = title !== ''

  const permissions = useResource(
    useCallback(
      (signal: AbortSignal) => api.permissions.paged({ page, pageSize }, filters, signal),
      [page, pageSize, filters],
    ),
  )

  useEffect(() => {
    setPage(1)
  }, [filters, pageSize])

  const columns = useMemo<Column<Permission>[]>(
    () => [
      {
        key: 'title',
        header: fa.permissions.colTitle,
        cell: (permission) => <span className="font-medium text-ink">{permission.title}</span>,
      },
      {
        key: 'name',
        header: fa.permissions.colName,
        cell: (permission) => <span className="latin text-ink-soft">{permission.name}</span>,
      },
      {
        key: 'group',
        header: fa.permissions.colGroup,
        cell: (permission) => (
          <Badge tone="neutral">{permissionGroupTitle(permissionResource(permission.name))}</Badge>
        ),
      },
      {
        key: 'created',
        header: fa.table.createdOn,
        className: 'whitespace-nowrap',
        cell: (permission) => <AuditCell date={permission.creationDate} actor={permission.userCreatedName} />,
      },
    ],
    [],
  )

  return (
    <div className="space-y-5">
      <PageHeader title={fa.permissions.title} subtitle={fa.permissions.subtitle} />

      <Alert tone="info">{fa.permissions.readOnlyNote}</Alert>

      <FilterBar isFiltered={isFiltered} onClear={() => setTitle('')}>
        <Field label={fa.permissions.filterTitle}>
          {({ inputId }) => (
            <Input
              id={inputId}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              autoComplete="off"
            />
          )}
        </Field>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={permissions.data?.items ?? []}
        rowKey={(permission) => permission.id}
        isLoading={permissions.isLoading}
        isRefreshing={permissions.isRefreshing}
        error={permissions.error}
        emptyTitle={fa.permissions.emptyTitle}
        emptyBody={fa.permissions.emptyBody}
        skeletonRows={Math.min(pageSize, 8)}
        emptyAction={
          isFiltered ? (
            <Button variant="outline" size="sm" onClick={() => setTitle('')}>
              {fa.table.clearFilters}
            </Button>
          ) : undefined
        }
      />

      <Pagination
        page={page}
        pageSize={pageSize}
        totalRecords={permissions.data?.totalRecords ?? 0}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
        isBusy={permissions.isLoading || permissions.isRefreshing}
      />
    </div>
  )
}
