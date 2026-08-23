import { useCallback, useEffect, useMemo, useState } from 'react'
import { PERMISSIONS, can } from '../auth/permissions'
import { useAuth } from '../auth/AuthContext'
import { isSystemUser } from '../auth/systemEntities'
import { AuditCell } from '../components/admin/AuditCell'
import { FilterBar } from '../components/admin/FilterBar'
import { PageHeader } from '../components/admin/PageHeader'
import { UserFormModal } from '../components/users/UserFormModal'
import { Alert } from '../components/ui/Alert'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Field } from '../components/ui/Field'
import { IconButton } from '../components/ui/IconButton'
import { Input } from '../components/ui/Input'
import { Pagination } from '../components/ui/Pagination'
import { Select } from '../components/ui/Select'
import { fa } from '../i18n/fa'
import { api } from '../lib/api'
import type { User, UserFilters, UserTypeName } from '../lib/apiTypes'
import { ABSENT } from '../lib/format'
import { useDebounced } from '../lib/useDebounced'
import { useResource } from '../lib/useResource'

/**
 * The user listing: filter, page, create/edit, and the four state actions.
 *
 * **Every action is gated twice.** `can()` decides whether the button is drawn, and the server decides
 * whether it works — the second one is the security boundary and the first is only there so the screen
 * does not offer controls that always fail. `cs-admin` is the extreme case: all four of its actions are
 * refused by username, so the row shows a badge saying so instead of four buttons.
 *
 * **The confirm dialogs are one component, not five.** Activate, deactivate, reset-password and delete
 * differ only in their wording and the one call they make, so `CONFIRMS` holds that difference as data
 * and `ConfirmDialog` is mounted once. Each entry owns its own success sentence, which is what the page
 * shows after refetching.
 */

/** The status filter is one control over two independent server flags, so it is its own little enum. */
type StatusFilter = '' | 'active' | 'inactive' | 'locked'

const USER_TYPES: UserTypeName[] = ['Administrator', 'Trader', 'Analyst', 'Viewer']

/** Anything that opens over the table. `null` is the table by itself. */
type Dialog =
  | { kind: 'create' }
  | { kind: 'edit'; user: User }
  | { kind: 'activate'; user: User }
  | { kind: 'deactivate'; user: User }
  | { kind: 'reset'; user: User }
  | { kind: 'delete'; user: User }
  | null

type ConfirmKind = 'activate' | 'deactivate' | 'reset' | 'delete'

const CONFIRMS: Record<
  ConfirmKind,
  {
    title: string
    body: string
    confirmLabel: string
    tone: 'danger' | 'primary'
    run: (user: User) => Promise<unknown>
    notice: string
  }
> = {
  activate: {
    title: fa.users.confirmActivateTitle,
    body: fa.users.confirmActivateBody,
    confirmLabel: fa.users.activate,
    // Reversible in one click, so it is not dressed up as destructive.
    tone: 'primary',
    run: (user) => api.users.activate(user.id),
    notice: fa.users.activatedSuccess,
  },
  deactivate: {
    title: fa.users.confirmDeactivateTitle,
    body: fa.users.confirmDeactivateBody,
    confirmLabel: fa.users.deactivate,
    tone: 'danger',
    run: (user) => api.users.deactivate(user.id),
    notice: fa.users.deactivatedSuccess,
  },
  reset: {
    title: fa.users.confirmResetTitle,
    body: fa.users.confirmResetBody,
    confirmLabel: fa.users.resetPassword,
    tone: 'danger',
    run: (user) => api.users.resetPassword(user.id),
    notice: fa.users.resetSuccess,
  },
  delete: {
    title: fa.users.confirmDeleteTitle,
    body: fa.users.confirmDeleteBody,
    confirmLabel: fa.common.delete,
    tone: 'danger',
    run: (user) => api.users.remove(user.id),
    notice: fa.users.deletedSuccess,
  },
}

export function UsersPage() {
  const { session } = useAuth()

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  const [userName, setUserName] = useState('')
  const [fullName, setFullName] = useState('')
  const [status, setStatus] = useState<StatusFilter>('')
  const [userType, setUserType] = useState<UserTypeName | ''>('')

  const [dialog, setDialog] = useState<Dialog>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // Typing is debounced; the two selects are not — a select changes once, deliberately, and waiting
  // 350ms after a click reads as lag.
  const debouncedUserName = useDebounced(userName)
  const debouncedFullName = useDebounced(fullName)

  const filters = useMemo<UserFilters>(
    () => ({
      UserName: debouncedUserName.trim() || undefined,
      FullName: debouncedFullName.trim() || undefined,
      UserType: userType || undefined,
      // Tri-state, and `undefined` is not `false`: sending `IsActive=` fails to bind to `bool?` and
      // 400s the whole listing, so an unset filter has to be absent from the query string entirely.
      IsActive: status === 'active' ? true : status === 'inactive' ? false : undefined,
      IsLocked: status === 'locked' ? true : undefined,
    }),
    [debouncedUserName, debouncedFullName, userType, status],
  )

  const isFiltered = userName !== '' || fullName !== '' || status !== '' || userType !== ''

  const users = useResource(
    useCallback(
      (signal: AbortSignal) => api.users.paged({ page, pageSize }, filters, signal),
      [page, pageSize, filters],
    ),
  )

  // A filter that narrows the result set while the reader is on page 4 would otherwise land them on an
  // empty page and look like "no results".
  useEffect(() => {
    setPage(1)
  }, [filters, pageSize])

  const clearFilters = () => {
    setUserName('')
    setFullName('')
    setStatus('')
    setUserType('')
  }

  const succeed = (message: string) => {
    setNotice(message)
    setDialog(null)
    users.refetch()
  }

  const columns = useMemo<Column<User>[]>(
    () => [
      {
        key: 'user',
        header: fa.users.colUser,
        cell: (user) => (
          <div className="leading-tight">
            <span className="block font-medium text-ink">{user.fullName}</span>
            <span className="latin mt-1 block text-xs text-ink-muted">{user.userName}</span>
          </div>
        ),
      },
      {
        key: 'roles',
        header: fa.users.colRoles,
        cell: (user) =>
          user.roles && user.roles.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {user.roles.map((role) => (
                <Badge key={role.id} tone="neutral">
                  {role.title}
                </Badge>
              ))}
            </div>
          ) : (
            <span className="text-ink-muted">{fa.users.noRoles}</span>
          ),
      },
      {
        key: 'type',
        header: fa.users.colType,
        cell: (user) => <span className="latin text-ink-soft">{user.userType ?? ABSENT}</span>,
      },
      {
        key: 'status',
        header: fa.users.colStatus,
        cell: (user) => (
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={user.isActive ? 'success' : 'neutral'}>
              {user.isActive ? fa.common.active : fa.common.inactive}
            </Badge>
            {user.isLocked && <Badge tone="warn">{fa.common.locked}</Badge>}
          </div>
        ),
      },
      {
        key: 'created',
        header: fa.table.createdOn,
        className: 'whitespace-nowrap',
        cell: (user) => <AuditCell date={user.creationDate} actor={user.userCreatedName} />,
      },
      {
        key: 'actions',
        header: fa.table.actions,
        align: 'end',
        className: 'whitespace-nowrap',
        cell: (user) =>
          isSystemUser(user) ? (
            // The four server actions are all refused by username for this account, so the row
            // explains itself instead of offering controls that can only ever error.
            <span title={fa.users.systemAccountNote}>
              <Badge tone="accent">{fa.users.systemAccount}</Badge>
            </span>
          ) : (
            <div className="flex items-center justify-end gap-1">
              {can(session, PERMISSIONS.userUpdate) && (
                <IconButton label={fa.common.edit} onClick={() => setDialog({ kind: 'edit', user })}>
                  <EditIcon />
                </IconButton>
              )}

              {user.isActive
                ? can(session, PERMISSIONS.userDeactivate) && (
                    <IconButton
                      label={fa.users.deactivate}
                      onClick={() => setDialog({ kind: 'deactivate', user })}
                    >
                      <BlockIcon />
                    </IconButton>
                  )
                : can(session, PERMISSIONS.userActivate) && (
                    <IconButton
                      label={fa.users.activate}
                      onClick={() => setDialog({ kind: 'activate', user })}
                    >
                      <CheckIcon />
                    </IconButton>
                  )}

              {can(session, PERMISSIONS.userResetPassword) && (
                <IconButton
                  label={fa.users.resetPassword}
                  onClick={() => setDialog({ kind: 'reset', user })}
                >
                  <KeyIcon />
                </IconButton>
              )}

              {can(session, PERMISSIONS.userDelete) && (
                <IconButton label={fa.users.deleteUser} onClick={() => setDialog({ kind: 'delete', user })}>
                  <TrashIcon />
                </IconButton>
              )}
            </div>
          ),
      },
    ],
    [session],
  )

  // Carrying the row alongside its wording is what lets TypeScript prove `.user` exists here — the
  // `create` variant has no user, and a separate `confirm` lookup would not narrow `dialog` with it.
  const confirm =
    dialog && dialog.kind !== 'create' && dialog.kind !== 'edit'
      ? { ...CONFIRMS[dialog.kind], user: dialog.user }
      : null

  return (
    <div className="space-y-5">
      <PageHeader
        title={fa.users.title}
        subtitle={fa.users.subtitle}
        actions={
          can(session, PERMISSIONS.userCreate) && (
            <Button onClick={() => setDialog({ kind: 'create' })}>{fa.users.createButton}</Button>
          )
        }
      />

      {notice && (
        <Alert tone="success">
          {notice}
        </Alert>
      )}

      <FilterBar isFiltered={isFiltered} onClear={clearFilters}>
        <Field label={fa.users.filterUserName}>
          {({ inputId }) => (
            <Input
              id={inputId}
              value={userName}
              onChange={(event) => setUserName(event.target.value)}
              autoComplete="off"
              dir="ltr"
              className="latin"
            />
          )}
        </Field>

        <Field label={fa.users.filterFullName}>
          {({ inputId }) => (
            <Input
              id={inputId}
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              autoComplete="off"
            />
          )}
        </Field>

        <Field label={fa.users.filterStatus}>
          {({ inputId }) => (
            <Select id={inputId} value={status} onChange={(event) => setStatus(event.target.value as StatusFilter)}>
              <option value="">{fa.common.all}</option>
              <option value="active">{fa.common.active}</option>
              <option value="inactive">{fa.common.inactive}</option>
              <option value="locked">{fa.common.locked}</option>
            </Select>
          )}
        </Field>

        <Field label={fa.users.filterType}>
          {({ inputId }) => (
            <Select
              id={inputId}
              value={userType}
              onChange={(event) => setUserType(event.target.value as UserTypeName | '')}
            >
              <option value="">{fa.common.all}</option>
              {USER_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={users.data?.items ?? []}
        rowKey={(user) => user.id}
        isLoading={users.isLoading}
        isRefreshing={users.isRefreshing}
        error={users.error}
        emptyTitle={fa.users.emptyTitle}
        emptyBody={fa.users.emptyBody}
        skeletonRows={Math.min(pageSize, 8)}
        emptyAction={
          isFiltered ? (
            <Button variant="outline" size="sm" onClick={clearFilters}>
              {fa.table.clearFilters}
            </Button>
          ) : undefined
        }
      />

      <Pagination
        page={page}
        pageSize={pageSize}
        totalRecords={users.data?.totalRecords ?? 0}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
        isBusy={users.isLoading || users.isRefreshing}
      />

      {/* Mounted only while open, so the role and parent lists are fetched fresh each time rather than
          held stale from the first time the dialog was used. */}
      {dialog?.kind === 'create' && (
        <UserFormModal user={null} onClose={() => setDialog(null)} onSaved={succeed} />
      )}

      {dialog?.kind === 'edit' && (
        <UserFormModal user={dialog.user} onClose={() => setDialog(null)} onSaved={succeed} />
      )}

      {confirm && (
        <ConfirmDialog
          isOpen
          onClose={() => setDialog(null)}
          title={confirm.title}
          body={
            <>
              {confirm.body}
              <span className="mt-2 block font-medium text-ink">
                {confirm.user.fullName} (<span className="latin">{confirm.user.userName}</span>)
              </span>
            </>
          }
          confirmLabel={confirm.confirmLabel}
          tone={confirm.tone}
          onConfirm={async () => {
            await confirm.run(confirm.user)
            succeed(confirm.notice)
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

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" className="size-4.5" aria-hidden="true">
      <path d="M4 10.6l3.6 3.4L16 5.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function BlockIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className="size-4.5" aria-hidden="true">
      <circle cx="10" cy="10" r="6.9" />
      <path d="M5.2 14.8l9.6-9.6" strokeLinecap="round" />
    </svg>
  )
}

function KeyIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className="size-4.5" aria-hidden="true">
      <circle cx="7.2" cy="7.2" r="3.6" />
      <path d="M9.8 9.8l5.4 5.4M13 13l1.6 1.6M11.4 14.6l1.6 1.6" strokeLinecap="round" />
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
