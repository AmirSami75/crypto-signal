import { useCallback, useState } from 'react'
import { fa } from '../../i18n/fa'
import { api, errorDetails, errorMessage } from '../../lib/api'
import type { Role, RoleInput } from '../../lib/apiTypes'
import { groupPermissions } from '../../lib/permissionGroups'
import { useResource } from '../../lib/useResource'
import { Alert } from '../ui/Alert'
import { Button } from '../ui/Button'
import { Checkbox } from '../ui/Checkbox'
import { Field } from '../ui/Field'
import { Input } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { Skeleton } from '../ui/Skeleton'

/**
 * Create/edit form for a role — which in practice means the permission picker.
 *
 * **The picker is grouped by resource, with a per-group toggle.** The catalogue is sixteen rows today
 * and grows by one every time a controller gains a `[Permission]` action; a flat alphabetical column
 * would make "give this role everything about users" a scavenger hunt. `groupPermissions` owns both
 * the grouping and the section order, so this screen and the permission listing agree.
 *
 * **The permission set is replaced wholesale, not patched.** `RoleController.Update` deletes every
 * `RolePermission` row for the role and re-adds from the payload, so what is checked here is exactly
 * what the role will have — there is no "leave the rest alone" semantics to preserve.
 *
 * `name` is the non-localised identifier the seeder and any future code path match on, so it is a
 * left-to-right Latin field; `title` is what operators read in a table cell.
 */

type FormState = { name: string; title: string; permissionIds: string[] }

function initialState(role: Role | null): FormState {
  return {
    name: role?.name ?? '',
    title: role?.title ?? '',
    // Full nested permissions are only populated on the *role* endpoints; a role read out of a user
    // row would have null here. This dialog is always opened from the role listing, so they are there.
    permissionIds: role?.permissions?.map((permission) => permission.id) ?? [],
  }
}

export function RoleFormModal({
  role,
  onClose,
  onSaved,
}: {
  /** `null` to create. */
  role: Role | null
  onClose: () => void
  onSaved: (message: string) => void
}) {
  const isEditing = role !== null

  const [form, setForm] = useState<FormState>(() => initialState(role))
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<'name' | 'title' | 'permissions', string>>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [details, setDetails] = useState<string[]>([])
  const [isSaving, setIsSaving] = useState(false)

  const permissions = useResource(useCallback((signal: AbortSignal) => api.permissions.list(signal), []))
  const groups = groupPermissions(permissions.data ?? [])

  const setText = (key: 'name' | 'title', value: string) => {
    setForm((current) => ({ ...current, [key]: value }))
    setFieldErrors((current) => ({ ...current, [key]: undefined }))
  }

  const togglePermission = (permissionId: string, checked: boolean) => {
    setForm((current) => ({
      ...current,
      permissionIds: checked
        ? [...current.permissionIds, permissionId]
        : current.permissionIds.filter((id) => id !== permissionId),
    }))
    setFieldErrors((current) => ({ ...current, permissions: undefined }))
  }

  /** Whole group on or off in one click. Off removes only that group's ids, never the whole selection. */
  const toggleGroup = (ids: string[], checked: boolean) => {
    setForm((current) => {
      const kept = current.permissionIds.filter((id) => !ids.includes(id))
      return { ...current, permissionIds: checked ? [...kept, ...ids] : kept }
    })
    setFieldErrors((current) => ({ ...current, permissions: undefined }))
  }

  /** Client-side mirror of `RoleInputDto.Validate` plus the empty-set check `RoleController` makes. */
  const validate = (): boolean => {
    const next: Partial<Record<'name' | 'title' | 'permissions', string>> = {}

    const name = form.name.trim()
    const title = form.title.trim()

    if (name.length === 0) next.name = fa.validation.roleNameRequired
    else if (name.length > 100) next.name = fa.validation.roleNameTooLong

    if (title.length === 0) next.title = fa.validation.roleTitleRequired
    else if (title.length > 100) next.title = fa.validation.roleTitleTooLong

    if (form.permissionIds.length === 0) next.permissions = fa.validation.permissionsRequired

    setFieldErrors(next)
    return Object.keys(next).length === 0
  }

  const submit = async () => {
    setFormError(null)
    setDetails([])
    if (!validate()) return

    const payload: RoleInput = {
      name: form.name.trim(),
      title: form.title.trim(),
      permissions: form.permissionIds.map((id) => ({ id })),
    }

    setIsSaving(true)
    try {
      if (isEditing) {
        await api.roles.update({ ...payload, id: role.id })
        onSaved(fa.roles.updatedSuccess)
      } else {
        await api.roles.create(payload)
        onSaved(fa.roles.createdSuccess)
      }
    } catch (cause) {
      setFormError(errorMessage(cause))
      setDetails(errorDetails(cause))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={isEditing ? fa.roles.editTitle : fa.roles.createTitle}
      size="lg"
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={isSaving}>
            {fa.common.cancel}
          </Button>
          <Button onClick={submit} isLoading={isSaving}>
            {fa.common.save}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {formError && (
          <Alert tone="error" details={details}>
            {formError}
          </Alert>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={fa.roles.name} required error={fieldErrors.name} hint={fa.roles.nameHint}>
            {({ inputId, describedBy, isInvalid }) => (
              <Input
                id={inputId}
                aria-describedby={describedBy}
                isInvalid={isInvalid}
                value={form.name}
                onChange={(event) => setText('name', event.target.value)}
                autoComplete="off"
                dir="ltr"
                className="latin"
              />
            )}
          </Field>

          <Field label={fa.roles.roleTitle} required error={fieldErrors.title} hint={fa.roles.roleTitleHint}>
            {({ inputId, describedBy, isInvalid }) => (
              <Input
                id={inputId}
                aria-describedby={describedBy}
                isInvalid={isInvalid}
                value={form.title}
                onChange={(event) => setText('title', event.target.value)}
                autoComplete="off"
              />
            )}
          </Field>
        </div>

        <fieldset className="space-y-2">
          <legend className="text-[0.8125rem] font-medium text-ink-soft">
            {fa.roles.permissions}
            <span className="ms-1 text-danger" aria-hidden="true">
              *
            </span>
          </legend>

          {permissions.isLoading ? (
            <div className="space-y-2 rounded-xl border border-line p-4">
              <Skeleton className="h-5 w-32" />
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-5 w-40" />
            </div>
          ) : permissions.error ? (
            <Alert tone="error">{permissions.error}</Alert>
          ) : (
            <div className="space-y-3">
              {groups.map((group) => {
                const ids = group.permissions.map((permission) => permission.id)
                const selected = ids.filter((id) => form.permissionIds.includes(id)).length
                const allSelected = selected === ids.length

                return (
                  <div key={group.resource} className="rounded-xl border border-line">
                    <div className="flex items-center justify-between gap-3 border-b border-line px-3 py-2">
                      <span className="text-sm font-medium text-ink">
                        {group.title}
                        <span className="num ms-2 text-xs font-normal text-ink-muted">
                          {selected}/{ids.length}
                        </span>
                      </span>

                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleGroup(ids, !allSelected)}
                        type="button"
                      >
                        {allSelected ? fa.common.clearAll : fa.common.selectAll}
                      </Button>
                    </div>

                    <div className="p-1.5">
                      {group.permissions.map((permission) => (
                        <Checkbox
                          key={permission.id}
                          checked={form.permissionIds.includes(permission.id)}
                          onChange={(checked) => togglePermission(permission.id, checked)}
                          label={permission.title}
                          description={<span className="latin">{permission.name}</span>}
                        />
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {fieldErrors.permissions ? (
            <p role="alert" className="text-xs text-danger-ink">
              {fieldErrors.permissions}
            </p>
          ) : (
            <p className="text-xs text-ink-muted">{fa.roles.permissionsHint}</p>
          )}
        </fieldset>
      </div>
    </Modal>
  )
}
