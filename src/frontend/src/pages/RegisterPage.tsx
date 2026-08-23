import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { fa } from '../i18n/fa'
import { useAuth } from '../auth/AuthContext'
import { errorDetails, errorMessage } from '../lib/api'
import { toLatinDigits } from '../lib/digits'
import { Alert } from '../components/ui/Alert'
import { Button, buttonClasses } from '../components/ui/Button'
import { Field } from '../components/ui/Field'
import { Input } from '../components/ui/Input'
import { PasswordInput } from '../components/ui/PasswordInput'
import { PasswordRules, isPasswordStrong } from '../components/PasswordRules'
import { ROUTES } from '../routes'

/**
 * `POST /api/v1/auth/register` — the one anonymous write endpoint.
 *
 * A successful registration establishes **no session**. The server creates the account inactive, with
 * no roles, and `Login` refuses an inactive account outright, so the honest thing to show afterwards
 * is not a dashboard but an explanation that an administrator has to activate it. That is why success
 * replaces the form rather than navigating: sending the user to /login would imply they can now sign
 * in, and they cannot.
 *
 * The request body carries only the six fields below. `roles`, `userType`, `isActive` and friends are
 * absent from the server's `RegisterDto` on purpose — sending them has no effect — so there is
 * nothing here that could escalate a self-registration into a privileged account.
 */

type FieldErrors = {
  fullName?: string
  userName?: string
  password?: string
  confirmPassword?: string
}

export function RegisterPage() {
  const { register } = useAuth()

  const [fullName, setFullName] = useState('')
  const [userName, setUserName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [email, setEmail] = useState('')
  const [mobile, setMobile] = useState('')

  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [details, setDetails] = useState<string[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isRegistered, setIsRegistered] = useState(false)

  const controllerRef = useRef<AbortController | null>(null)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    // Mirrors `RegisterDto.Validate` for the rules that can be mirrored exactly, using its exact
    // wording. Email and mobile are left to the server: their patterns are .NET regexes, and a
    // slightly-wrong transcription here would block a valid address rather than merely cost a round
    // trip — the wrong way to be wrong for an optional field.
    const nextFieldErrors: FieldErrors = {}
    if (!fullName.trim()) nextFieldErrors.fullName = fa.validation.fullNameRequired
    if (!userName.trim()) nextFieldErrors.userName = fa.validation.userNameRequired

    if (!password) nextFieldErrors.password = fa.validation.passwordRequired
    else if (!isPasswordStrong(password)) nextFieldErrors.password = fa.validation.passwordWeak

    if (!confirmPassword) nextFieldErrors.confirmPassword = fa.validation.confirmPasswordRequired
    else if (password !== confirmPassword) nextFieldErrors.confirmPassword = fa.validation.passwordMismatch

    setFieldErrors(nextFieldErrors)
    if (Object.keys(nextFieldErrors).length > 0) return

    setFormError(null)
    setDetails([])
    setIsSubmitting(true)

    const controller = new AbortController()
    controllerRef.current?.abort()
    controllerRef.current = controller

    try {
      await register(
        {
          fullName: fullName.trim(),
          userName: userName.trim(),
          password,
          confirmPassword,
          // Undefined rather than '' for the optional fields: the server skips validation on
          // null-or-empty, and an empty string would be stored as an empty contact detail.
          email: email.trim() || undefined,
          mobile: toLatinDigits(mobile.trim()) || undefined,
        },
        controller.signal,
      )
      setIsRegistered(true)
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setFormError(errorMessage(error))
      setDetails(errorDetails(error))
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isRegistered) {
    return (
      <div>
        <Alert tone="success" title={fa.auth.registerSuccessTitle}>
          {fa.auth.registerSuccessBody}
        </Alert>

        <Link
          to={ROUTES.login}
          className={buttonClasses({ variant: 'secondary', size: 'lg', fullWidth: true, className: 'mt-6' })}
        >
          {fa.auth.backToLogin}
        </Link>
      </div>
    )
  }

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-[1.375rem] font-semibold">{fa.auth.registerTitle}</h1>
        <p className="mt-1.5 text-sm text-ink-muted">{fa.auth.registerSubtitle}</p>
      </header>

      {formError && (
        <Alert tone="error" details={details} className="mb-5">
          {formError}
        </Alert>
      )}

      <form onSubmit={handleSubmit} noValidate className="space-y-5">
        <Field label={fa.auth.fullName} error={fieldErrors.fullName} required>
          {({ inputId, describedBy, isInvalid }) => (
            <Input
              id={inputId}
              aria-describedby={describedBy}
              isInvalid={isInvalid}
              name="name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              placeholder={fa.auth.fullNamePlaceholder}
              autoComplete="name"
              autoFocus
              disabled={isSubmitting}
            />
          )}
        </Field>

        <Field label={fa.auth.userName} error={fieldErrors.userName} required>
          {({ inputId, describedBy, isInvalid }) => (
            <Input
              id={inputId}
              aria-describedby={describedBy}
              isInvalid={isInvalid}
              name="username"
              value={userName}
              onChange={(event) => setUserName(event.target.value)}
              placeholder={fa.auth.userNamePlaceholder}
              autoComplete="username"
              dir="ltr"
              className="text-start"
              disabled={isSubmitting}
            />
          )}
        </Field>

        <Field label={fa.auth.password} error={fieldErrors.password} required>
          {({ inputId, describedBy, isInvalid }) => (
            <PasswordInput
              id={inputId}
              aria-describedby={describedBy}
              isInvalid={isInvalid}
              name="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              disabled={isSubmitting}
            />
          )}
        </Field>

        <Field label={fa.auth.confirmPassword} error={fieldErrors.confirmPassword} required>
          {({ inputId, describedBy, isInvalid }) => (
            <PasswordInput
              id={inputId}
              aria-describedby={describedBy}
              isInvalid={isInvalid}
              name="confirm-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              autoComplete="new-password"
              disabled={isSubmitting}
            />
          )}
        </Field>

        <PasswordRules password={password} confirmPassword={confirmPassword} />

        <Field label={fa.auth.email} hint={fa.common.optional}>
          {({ inputId, describedBy }) => (
            <Input
              id={inputId}
              aria-describedby={describedBy}
              type="email"
              name="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder={fa.auth.emailPlaceholder}
              autoComplete="email"
              dir="ltr"
              className="text-start"
              disabled={isSubmitting}
            />
          )}
        </Field>

        <Field label={fa.auth.mobile} hint={`${fa.common.optional} — ${fa.auth.mobileHint}`}>
          {({ inputId, describedBy }) => (
            <Input
              id={inputId}
              aria-describedby={describedBy}
              type="tel"
              inputMode="numeric"
              name="tel"
              value={mobile}
              onChange={(event) => setMobile(event.target.value)}
              placeholder={fa.auth.mobilePlaceholder}
              autoComplete="tel"
              dir="ltr"
              className="text-start"
              disabled={isSubmitting}
            />
          )}
        </Field>

        <Button type="submit" size="lg" fullWidth isLoading={isSubmitting}>
          {isSubmitting ? fa.auth.submittingRegister : fa.auth.submitRegister}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-ink-muted">
        {fa.auth.haveAccount}{' '}
        <Link to={ROUTES.login} className="font-semibold text-accent-ink hover:underline">
          {fa.auth.goToLogin}
        </Link>
      </p>
    </div>
  )
}
