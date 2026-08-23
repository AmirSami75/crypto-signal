import { useRef, useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router'
import { fa } from '../i18n/fa'
import { useAuth } from '../auth/AuthContext'
import { errorDetails, errorMessage } from '../lib/api'
import { Alert } from '../components/ui/Alert'
import { Button, buttonClasses } from '../components/ui/Button'
import { Field } from '../components/ui/Field'
import { PasswordInput } from '../components/ui/PasswordInput'
import { PasswordRules, isPasswordStrong } from '../components/PasswordRules'
import { Spinner } from '../components/ui/Spinner'
import { ROUTES } from '../routes'

/**
 * `PUT /api/v1/auth/change-password`.
 *
 * Two entry points, one screen: the seeded `cs-admin` arrives here because it carries
 * `requiresPasswordChange` and cannot get anywhere else, and anyone else can arrive from the user
 * menu. Only the heading copy differs.
 *
 * **This page gates itself instead of sitting behind `RequireAuth`.** A successful change rotates the
 * user's security stamp server-side, which kills the token in hand — so `AuthContext.changePassword`
 * clears the session, by necessity rather than by choice. Under the shared guard that clearing would
 * immediately redirect to /login and race the very message explaining what just happened. Owning the
 * three states here makes the order deterministic: success is shown, and the user leaves by choice.
 */

type FieldErrors = {
  currentPass?: string
  newPass?: string
  confirmNewPass?: string
}

export function ChangePasswordPage() {
  const { session, isRestoring, changePassword } = useAuth()

  const [currentPass, setCurrentPass] = useState('')
  const [newPass, setNewPass] = useState('')
  const [confirmNewPass, setConfirmNewPass] = useState('')

  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [details, setDetails] = useState<string[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isChanged, setIsChanged] = useState(false)

  // Kept for the success panel, which renders after the session has been cleared.
  const userNameRef = useRef(session?.userName ?? '')
  if (session) userNameRef.current = session.userName

  const controllerRef = useRef<AbortController | null>(null)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const nextFieldErrors: FieldErrors = {}

    // The server also requires the *current* password to satisfy `IsStrongPassword`, which is not
    // mirrored here on purpose: told "your current password is too weak", a user would reasonably
    // think they had mistyped it. If it ever comes up, the server says so in its own words.
    if (!currentPass) nextFieldErrors.currentPass = fa.validation.passwordRequired

    if (!newPass) nextFieldErrors.newPass = fa.validation.newPasswordRequired
    else if (!isPasswordStrong(newPass)) nextFieldErrors.newPass = fa.validation.newPasswordWeak

    if (!confirmNewPass) nextFieldErrors.confirmNewPass = fa.validation.confirmNewPasswordRequired
    else if (newPass !== confirmNewPass) nextFieldErrors.confirmNewPass = fa.validation.newPasswordMismatch

    setFieldErrors(nextFieldErrors)
    if (Object.keys(nextFieldErrors).length > 0) return

    setFormError(null)
    setDetails([])
    setIsSubmitting(true)

    const controller = new AbortController()
    controllerRef.current?.abort()
    controllerRef.current = controller

    try {
      await changePassword({ currentPass, newPass, confirmNewPass }, controller.signal)
      setIsChanged(true)
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setFormError(errorMessage(error))
      setDetails(errorDetails(error))
    } finally {
      setIsSubmitting(false)
    }
  }

  // Checked before the session, because by this point there deliberately is none.
  if (isChanged) {
    return (
      <div>
        <Alert tone="success" title={fa.auth.changePasswordSuccess}>
          {fa.auth.changePasswordReLogin}
        </Alert>

        <Link
          to={ROUTES.login}
          // The username is carried across so the login form comes back pre-filled — the one thing
          // the user demonstrably still knows after changing the other half of their credentials.
          state={{ passwordChanged: true, userName: userNameRef.current }}
          replace
          className={buttonClasses({ size: 'lg', fullWidth: true, className: 'mt-6' })}
        >
          {fa.auth.submitLogin}
        </Link>
      </div>
    )
  }

  if (isRestoring) {
    return (
      <div className="flex justify-center py-10">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!session) return <Navigate to={ROUTES.login} replace />

  const isForced = session.requiresPasswordChange

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-[1.375rem] font-semibold">
          {isForced ? fa.auth.changePasswordForcedTitle : fa.auth.changePasswordTitle}
        </h1>
        <p className="mt-1.5 text-sm text-ink-muted">
          {isForced ? fa.auth.changePasswordForcedBody : fa.auth.changePasswordSubtitle}
        </p>
      </header>

      {/* Stated up front rather than as a surprise afterwards: the change ends this session. */}
      <Alert tone="info" className="mb-5">
        {fa.auth.changePasswordReLogin}
      </Alert>

      {formError && (
        <Alert tone="error" details={details} className="mb-5">
          {formError}
        </Alert>
      )}

      <form onSubmit={handleSubmit} noValidate className="space-y-5">
        <Field label={fa.auth.currentPassword} error={fieldErrors.currentPass} required>
          {({ inputId, describedBy, isInvalid }) => (
            <PasswordInput
              id={inputId}
              aria-describedby={describedBy}
              isInvalid={isInvalid}
              name="current-password"
              value={currentPass}
              onChange={(event) => setCurrentPass(event.target.value)}
              autoComplete="current-password"
              autoFocus
              disabled={isSubmitting}
            />
          )}
        </Field>

        <Field label={fa.auth.newPassword} error={fieldErrors.newPass} required>
          {({ inputId, describedBy, isInvalid }) => (
            <PasswordInput
              id={inputId}
              aria-describedby={describedBy}
              isInvalid={isInvalid}
              name="new-password"
              value={newPass}
              onChange={(event) => setNewPass(event.target.value)}
              autoComplete="new-password"
              disabled={isSubmitting}
            />
          )}
        </Field>

        <Field label={fa.auth.confirmNewPassword} error={fieldErrors.confirmNewPass} required>
          {({ inputId, describedBy, isInvalid }) => (
            <PasswordInput
              id={inputId}
              aria-describedby={describedBy}
              isInvalid={isInvalid}
              name="confirm-new-password"
              value={confirmNewPass}
              onChange={(event) => setConfirmNewPass(event.target.value)}
              autoComplete="new-password"
              disabled={isSubmitting}
            />
          )}
        </Field>

        <PasswordRules password={newPass} confirmPassword={confirmNewPass} />

        <Button type="submit" size="lg" fullWidth isLoading={isSubmitting}>
          {isSubmitting ? fa.auth.submittingChangePassword : fa.auth.submitChangePassword}
        </Button>
      </form>

      {/* A forced change has no way out but through it, so no escape hatch is offered there. */}
      {!isForced && (
        <p className="mt-6 text-center text-sm">
          <Link to={ROUTES.overview} className="text-ink-muted hover:text-accent-ink hover:underline">
            {fa.common.cancel}
          </Link>
        </p>
      )}
    </div>
  )
}
