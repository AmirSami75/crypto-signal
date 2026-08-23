import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { PERMISSIONS, can } from '../auth/permissions'
import { isSystemRole } from '../auth/systemEntities'
import { AuditCell } from '../components/admin/AuditCell'
import { FilterBar } from '../components/admin/FilterBar'
import { PageHeader } from '../components/admin/PageHeader'
import { RoleFormModal } from '../components/roles/RoleFormModal'
import { Alert } from '../components/ui/Alert'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Field } from '../components/ui/Field'
import { IconButton } from '../components/ui/IconButton'
import { Input } from '../components/ui/Input'
import { Pagination } from '../components/ui/Pagination'
import { fa } from '../i18n/fa'
import { api } from '../lib/api'
import type { Role, TitleFilter } from '../lib/apiTypes'
import { ABSENT } from '../lib/format'
import { useDebounced } from '../lib/useDebounced'
import { useResource } from '../lib/useResource'

/**
 * The role listing.
 *
 * The permission count is rendered rather than the permissions themselves: a role can hold all sixteen,
 * and sixteen badges in a table cell push every other column off the screen. The set is one click away
 * in the edit dialog, which is also where it can be changed.
 *
 * `SuperAdmin` and `User` are seeded and the server refuses to edit or delete either, so those rows
 * carry a badge in place of the two buttons — see `auth/systemEntities.ts` for why that is a courtesy
 * and not a control.
 */

type Dialog = { kind: 'create' } | { kind: 'edit'; role: Role } | { kind: 'delete'; role: Role } | null

export function RolesPage() {
  const { session } = useAuth()

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [title, setTitle] = useState('')

  const [dialog, setDialog] = useState<Dialog>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const debouncedTitle = useDebounced(title)

  const filters = useMemo<TitleFilter>(() => ({ Title: debouncedTitle.trim() || undefined }), [debouncedTitle])

  const isFiltered = title !== ''

  const roles = useResource(
    useCallback(
      (signal: AbortSignal) => api.roles.paged({ page, pageSize }, filters, signal),
      [page, pageSize, filters],
    ),
  )

  useEffect(() => {
    setPage(1)
  }, [filters, pageSize])

  const succeed = (message: string) => {
    setNotice(message)
    setDialog(null)
    roles.refetch()
  }

  const columns = useMemo<Column<Role>[]>(
    () => [
      {
        key: 'role',
        header: fa.roles.colRole,
        cell: (role) => (
          <div className="leading-tight">
            <span className="block font-medium text-ink">{role.title}</span>
            <span className="latin mt-1 block text-xs text-ink-muted">{role.name}</span>
          </div>
        ),
      },
      {
        key: 'type',
        header: fa.roles.colType,
        cell: (role) => <span className="text-ink-soft">{role.type ?? ABSENT}</span>,
      },
      {
        key: 'permissions',
        header: fa.roles.colPermissions,
        cell: (role) =>
          role.permissions && role.permissions.length > 0 ? (
            <span className="text-ink-soft">
              <span className="num">{role.permissions.length}</span>
              <span className="ms-1">{fa.roles.permissionCount}</span>
            </span>
          ) : (
            <span className="text-ink-muted">{fa.roles.noPermissions}</span>
          ),
      },
      {
        key: 'created',
        header: fa.table.createdOn,
        className: 'whitespace-nowrap',
        cell: (role) => <AuditCell date={role.creationDate} actor={role.userCreatedName} />,
      },
      {
        key: 'actions',
        header: fa.table.actions,
        align: 'end',
        className: 'whitespace-nowrap',
        cell: (role) =>
          isSystemRole(role) ? (
            <span title={fa.roles.systemRoleNote}>
              <Badge tone="accent">{fa.roles.systemRole}</Badge>
            </span>
          ) : (
            <div className="flex items-center justify-end gap-1">
              {can(session, PERMISSIONS.roleUpdate) && (
                <IconButton label={fa.common.edit} onClick={() => setDialog({ kind: 'edit', role })}>
                  <EditIcon />
                </IconButton>
              )}

              {can(session, PERMISSIONS.roleDelete) && (
                <IconButton label={fa.roles.deleteRole} onClick={() => setDialog({ kind: 'delete', role })}>
                  <TrashIcon />
                </IconButton>
              )}
            </div>
          ),
      },
    ],
    [session],
  )

  return (
    <div className="space-y-5">
      <PageHeader
        title={fa.roles.title}
        subtitle={fa.roles.subtitle}
        actions={
          can(session, PERMISSIONS.roleCreate) && (
            <Button onClick={() => setDialog({ kind: 'create' })}>{fa.roles.createButton}</Button>
          )
        }
      />

      {notice && <Alert tone="success">{notice}</Alert>}

      <FilterBar isFiltered={isFiltered} onClear={() => setTitle('')}>
        <Field label={fa.roles.filterTitle}>
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
        rows={roles.data?.items ?? []}
        rowKey={(role) => role.id}
        isLoading={roles.isLoading}
        isRefreshing={roles.isRefreshing}
        error={roles.error}
        emptyTitle={fa.roles.emptyTitle}
        emptyBody={fa.roles.emptyBody}
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
        totalRecords={roles.data?.totalRecords ?? 0}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
        isBusy={roles.isLoading || roles.isRefreshing}
      />

      {dialog?.kind === 'create' && (
        <RoleFormModal role={null} onClose={() => setDialog(null)} onSaved={succeed} />
      )}

      {dialog?.kind === 'edit' && (
        <RoleFormModal role={dialog.role} onClose={() => setDialog(null)} onSaved={succeed} />
      )}

      {dialog?.kind === 'delete' && (
        <ConfirmDialog
          isOpen
          onClose={() => setDialog(null)}
          title={fa.roles.confirmDeleteTitle}
          body={
            <>
              {fa.roles.confirmDeleteBody}
              <span className="mt-2 block font-medium text-ink">
                {dialog.role.title} (<span className="latin">{dialog.role.name}</span>)
              </span>
            </>
          }
          confirmLabel={fa.common.delete}
          onConfirm={async () => {
            await api.roles.remove(dialog.role.id)
            succeed(fa.roles.deletedSuccess)
          }}
        />
      )}
    </div>
  )
}

function EditIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className="size-4.5" aria-hidden="true">
      <path d="M13.2 3.6l3.2 3.2-8.5 8.5-3.9.7.7-3.9 8.5-8.5z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className="size-4.5" aria-hidden="true">
      <path d="M4.4 6.2h11.2M8.2 4.2h3.6M6.3 6.2l.6 9.2h6.2l.6-9.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
