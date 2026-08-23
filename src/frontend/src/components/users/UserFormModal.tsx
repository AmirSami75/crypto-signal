import { useCallback, useState } from 'react'
import { fa } from '../../i18n/fa'
import { api, errorDetails, errorMessage } from '../../lib/api'
import type { User, UserInput, UserTypeName } from '../../lib/apiTypes'
import { useResource } from '../../lib/useResource'
import { Alert } from '../ui/Alert'
import { Button } from '../ui/Button'
import { Checkbox } from '../ui/Checkbox'
import { Field } from '../ui/Field'
import { Input } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { Select } from '../ui/Select'
import { Skeleton } from '../ui/Skeleton'

/**
 * Create/edit form for a user account.
 *
 * **There is no password field, and its absence is the design.** `BaseUserController.Create` hashes
 * `AuthGlobalVariables.DefaultPassword` itself and sets `RequirePasswordChange`, so the operator never
 * chooses, sees, or has to transmit a password — the new user signs in with the platform default and
 * is forced to change it on the spot. A field here would have to either invent a value the server
 * ignores or ask for one the payload cannot carry.
 *
 * **The username is read-only when editing.** The server does allow it to change, but a username is
 * what login history, audit trails and the operator's own memory key on; renaming one silently
 * rewrites the identity behind every past sign-in row. Nothing needs that badly enough to be one
 * keystroke away, and re-creating the account is the honest way to do it.
 *
 * Roles and the parent picker are fetched unpaged when the dialog opens, which is what `api.roles.list`
 * and `api.users.list` are for. A paged fetch would give a permission picker that silently omits
 * whatever fell past page one.
 */

const USER_TYPES: UserTypeName[] = ['Administrator', 'Trader', 'Analyst', 'Viewer']

type FormState = {
  fullName: string
  userName: string
  email: string
  phone: string
  mobile: string
  personelCode: string
  address: string
  parentId: string
  userType: UserTypeName | ''
  roleIds: string[]
}

function initialState(user: User | null): FormState {
  return {
    fullName: user?.fullName ?? '',
    userName: user?.userName ?? '',
    email: user?.email ?? '',
    phone: user?.phone ?? '',
    mobile: user?.mobile ?? '',
    personelCode: user?.personelCode ?? '',
    address: user?.address ?? '',
    parentId: user?.parentId ?? '',
    userType: user?.userType ?? '',
    roleIds: user?.roles?.map((role) => role.id) ?? [],
  }
}

/** `''` for a field the server treats as absent — an empty string would fail its format checks. */
function orNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

export function UserFormModal({
  user,
  onClose,
  onSaved,
}: {
  /** `null` to create. */
  user: User | null
  onClose: () => void
  /** Called after a successful save, with the sentence the page should confirm with. */
  onSaved: (message: string) => void
}) {
  const isEditing = user !== null

  const [form, setForm] = useState<FormState>(() => initialState(user))
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof FormState, string>>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [details, setDetails] = useState<string[]>([])
  const [isSaving, setIsSaving] = useState(false)

  const roles = useResource(useCallback((signal: AbortSignal) => api.roles.list(signal), []))
  const users = useResource(useCallback((signal: AbortSignal) => api.users.list(signal), []))

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }))
    setFieldErrors((current) => ({ ...current, [key]: undefined }))
  }

  const toggleRole = (roleId: string, checked: boolean) => {
    setForm((current) => ({
      ...current,
      roleIds: checked ? [...current.roleIds, roleId] : current.roleIds.filter((id) => id !== roleId),
    }))
    setFieldErrors((current) => ({ ...current, roleIds: undefined }))
  }

  /**
   * Client-side mirror of `BaseUserInputDto.Validate`, limited to the rules that can be checked
   * without a database. Duplicate usernames and personnel codes are the server's to catch, and they
   * come back as a form-level message.
   */
  const validate = (): boolean => {
    const next: Partial<Record<keyof FormState, string>> = {}

    if (form.fullName.trim().length === 0) next.fullName = fa.validation.fullNameRequired
    if (form.userName.trim().length === 0) next.userName = fa.validation.userNameRequired
    if (form.roleIds.length === 0) next.roleIds = fa.validation.rolesRequired

    // Loose on purpose: this is a courtesy check ahead of `IsValidEmail`, not a second definition of
    // what an address is. Anything it lets through the server still judges.
    if (form.email.trim().length > 0 && !/^\S+@\S+\.\S+$/.test(form.email.trim()))
      next.email = fa.validation.emailInvalid

    if (form.personelCode.trim().length > 0 && !/^\d+$/.test(form.personelCode.trim()))
      next.personelCode = fa.validation.personelCodeDigits

    setFieldErrors(next)
    return Object.keys(next).length === 0
  }

  const submit = async () => {
    setFormError(null)
    setDetails([])
    if (!validate()) return

    const payload: UserInput = {
      fullName: form.fullName.trim(),
      userName: form.userName.trim(),
      email: orNull(form.email),
      phone: orNull(form.phone),
      mobile: orNull(form.mobile),
      personelCode: orNull(form.personelCode),
      address: orNull(form.address),
      parentId: orNull(form.parentId),
      userType: form.userType === '' ? null : form.userType,
      roles: form.roleIds.map((id) => ({ id })),
    }

    setIsSaving(true)
    try {
      if (isEditing) {
        await api.users.update({ ...payload, id: user.id })
        onSaved(fa.users.updatedSuccess)
      } else {
        await api.users.create(payload)
        onSaved(fa.users.createdSuccess)
      }
    } catch (cause) {
      setFormError(errorMessage(cause))
      setDetails(errorDetails(cause))
    } finally {
      setIsSaving(false)
    }
  }

  /**
   * Candidates for the parent picker.
   *
   * Two rows are removed because the server refuses them and the message it returns is a paragraph:
   * the user being edited (a user cannot be its own parent) and anyone whose parent is already this
   * user (that would close a two-node cycle). Deeper cycles are not checked — neither is the server's
   * check, which only looks one level up.
   */
  const parentCandidates = (users.data ?? []).filter(
    (candidate) => candidate.id !== user?.id && candidate.parentId !== user?.id,
  )

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={isEditing ? fa.users.editTitle : fa.users.createTitle}
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

        {!isEditing && <Alert tone="info">{fa.users.defaultPasswordNotice}</Alert>}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={fa.users.fullName} required error={fieldErrors.fullName}>
            {({ inputId, describedBy, isInvalid }) => (
              <Input
                id={inputId}
                aria-describedby={describedBy}
                isInvalid={isInvalid}
                value={form.fullName}
                onChange={(event) => set('fullName', event.target.value)}
                autoComplete="off"
              />
            )}
          </Field>

          <Field
            label={fa.users.userName}
            required
            error={fieldErrors.userName}
            hint={isEditing ? fa.users.userNameLocked : undefined}
          >
            {({ inputId, describedBy, isInvalid }) => (
              <Input
                id={inputId}
                aria-describedby={describedBy}
                isInvalid={isInvalid}
                value={form.userName}
                onChange={(event) => set('userName', event.target.value)}
                readOnly={isEditing}
                disabled={isEditing}
                autoComplete="off"
                dir="ltr"
                className="latin"
              />
            )}
          </Field>

          <Field label={fa.users.email} error={fieldErrors.email} hint={fa.common.optional}>
            {({ inputId, describedBy, isInvalid }) => (
              <Input
                id={inputId}
                type="email"
                aria-describedby={describedBy}
                isInvalid={isInvalid}
                value={form.email}
                onChange={(event) => set('email', event.target.value)}
                autoComplete="off"
                dir="ltr"
                className="latin"
              />
            )}
          </Field>

          <Field label={fa.users.mobile} error={fieldErrors.mobile} hint={fa.common.optional}>
            {({ inputId, describedBy, isInvalid }) => (
              <Input
                id={inputId}
                type="tel"
                inputMode="tel"
                aria-describedby={describedBy}
                isInvalid={isInvalid}
                value={form.mobile}
                onChange={(event) => set('mobile', event.target.value)}
                autoComplete="off"
                dir="ltr"
                className="num text-start"
              />
            )}
          </Field>

          <Field label={fa.users.phone} hint={fa.common.optional}>
            {({ inputId, describedBy }) => (
              <Input
                id={inputId}
                type="tel"
                inputMode="tel"
                aria-describedby={describedBy}
                value={form.phone}
                onChange={(event) => set('phone', event.target.value)}
                autoComplete="off"
                dir="ltr"
                className="num text-start"
              />
            )}
          </Field>

          <Field label={fa.users.personelCode} error={fieldErrors.personelCode} hint={fa.common.optional}>
            {({ inputId, describedBy, isInvalid }) => (
              <Input
                id={inputId}
                inputMode="numeric"
                aria-describedby={describedBy}
                isInvalid={isInvalid}
                value={form.personelCode}
                onChange={(event) => set('personelCode', event.target.value)}
                autoComplete="off"
                dir="ltr"
                className="num text-start"
              />
            )}
          </Field>

          <Field label={fa.users.userType} hint={fa.common.optional}>
            {({ inputId, describedBy }) => (
              <Select
                id={inputId}
                aria-describedby={describedBy}
                value={form.userType}
                onChange={(event) => set('userType', event.target.value as UserTypeName | '')}
              >
                <option value="">{fa.common.notSet}</option>
                {USER_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </Select>
            )}
          </Field>

          <Field label={fa.users.parent} hint={fa.common.optional}>
            {({ inputId, describedBy }) => (
              <Select
                id={inputId}
                aria-describedby={describedBy}
                value={form.parentId}
                onChange={(event) => set('parentId', event.target.value)}
                disabled={users.isLoading}
              >
                <option value="">{fa.users.parentNone}</option>
                {parentCandidates.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.fullName} ({candidate.userName})
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>

        <Field label={fa.users.address} hint={fa.common.optional}>
          {({ inputId, describedBy }) => (
            <Input
              id={inputId}
              aria-describedby={describedBy}
              value={form.address}
              onChange={(event) => set('address', event.target.value)}
              autoComplete="off"
            />
          )}
        </Field>

        <fieldset className="space-y-2">
          <legend className="text-[0.8125rem] font-medium text-ink-soft">
            {fa.users.roles}
            <span className="ms-1 text-danger" aria-hidden="true">
              *
            </span>
          </legend>

          <div className="rounded-xl border border-line p-1.5">
            {roles.isLoading ? (
              <div className="space-y-2 p-2">
                <Skeleton className="h-5 w-40" />
                <Skeleton className="h-5 w-32" />
              </div>
            ) : roles.error ? (
              <Alert tone="error" className="m-1">
                {roles.error}
              </Alert>
            ) : (roles.data ?? []).length === 0 ? (
              <p className="px-3 py-2.5 text-sm text-ink-muted">{fa.users.rolesEmpty}</p>
            ) : (
              (roles.data ?? []).map((role) => (
                <Checkbox
                  key={role.id}
                  checked={form.roleIds.includes(role.id)}
                  onChange={(checked) => toggleRole(role.id, checked)}
                  label={role.title}
                  description={<span className="latin">{role.name}</span>}
                />
              ))
            )}
          </div>

          {fieldErrors.roleIds ? (
            <p role="alert" className="text-xs text-danger-ink">
              {fieldErrors.roleIds}
            </p>
          ) : (
            <p className="text-xs text-ink-muted">{fa.users.rolesHint}</p>
          )}
        </fieldset>
      </div>
    </Modal>
  )
}
