import { useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { fa } from '../i18n/fa'
import { useAuth } from '../auth/AuthContext'
import { errorDetails, errorMessage } from '../lib/api'
import { Alert } from '../components/ui/Alert'
import { Button } from '../components/ui/Button'
import { Field } from '../components/ui/Field'
import { Input } from '../components/ui/Input'
import { PasswordInput } from '../components/ui/PasswordInput'
import { ROUTES } from '../routes'

/**
 * `POST /api/v1/auth/login`.
 *
 * The failure statuses here are not the ones a REST-shaped API would use — measured against the
 * running service, an unknown username answers **404**, a wrong password **422**, and a locked or
 * inactive account **403**. None of them is 401. So this page never interprets the status itself: it
 * renders whatever Persian sentence the API sent, which is already the most specific thing available.
 * `api.ts` is what guarantees that sentence is a sentence and not a serialised stack trace.
 */

type LoginLocationState = {
  /** Where the user was headed before the guard intercepted them. Set by `RequireAuth`. */
  from?: string
  /** Set by `ChangePasswordPage`, which ends the session and sends the user back here. */
  passwordChanged?: boolean
  userName?: string
}

/**
 * Only same-site paths are honoured as a post-login destination.
 *
 * `state.from` is written by our own guard, so this is belt-and-braces — but history state is
 * reachable from a crafted link, and `//evil.example` is a protocol-relative URL that `navigate`
 * would happily treat as off-site. One check is cheaper than trusting that it stays ours.
 */
function safeRedirect(from: string | undefined): string {
  if (!from) return ROUTES.overview
  if (!from.startsWith('/') || from.startsWith('//')) return ROUTES.overview
  return from
}

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const state = (location.state ?? null) as LoginLocationState | null

  const [userName, setUserName] = useState(state?.userName ?? '')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{ userName?: string; password?: string }>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [details, setDetails] = useState<string[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)

  const controllerRef = useRef<AbortController | null>(null)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    // Required-field checks only. Password *strength* is deliberately not checked on sign-in: the
    // rules may have tightened since the account was created, and refusing to even attempt a login
    // would lock out an account the server would still accept.
    const nextFieldErrors: { userName?: string; password?: string } = {}
    if (!userName.trim()) nextFieldErrors.userName = fa.validation.userNameRequired
    if (!password) nextFieldErrors.password = fa.validation.passwordRequired

    setFieldErrors(nextFieldErrors)
    if (Object.keys(nextFieldErrors).length > 0) return

    setFormError(null)
    setDetails([])
    setIsSubmitting(true)

    const controller = new AbortController()
    controllerRef.current?.abort()
    controllerRef.current = controller

    try {
      const session = await login({ userName: userName.trim(), password }, controller.signal)

      // The guard would redirect anyway, but doing it here keeps the forced-change hand-off in one
      // readable place instead of as a side effect of rendering.
      navigate(session.requiresPasswordChange ? ROUTES.changePassword : safeRedirect(state?.from), {
        replace: true,
      })
      // No `setIsSubmitting(false)`: this component unmounts on navigation, and clearing the flag
      // first would flash an enabled button on the way out.
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setFormError(errorMessage(error))
      setDetails(errorDetails(error))
      setIsSubmitting(false)
    }
  }

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-[1.375rem] font-semibold">{fa.auth.loginTitle}</h1>
        <p className="mt-1.5 text-sm text-ink-muted">{fa.auth.loginSubtitle}</p>
      </header>

      {state?.passwordChanged && (
        <Alert tone="success" title={fa.auth.changePasswordSuccess} className="mb-5">
          {fa.auth.changePasswordReLogin}
        </Alert>
      )}

      {formError && (
        <Alert tone="error" details={details} className="mb-5">
          {formError}
        </Alert>
      )}

      {/* noValidate: the browser's own validation bubbles are localised to the *browser's* language,
          which would put an English message on a Persian form. Every check is done here instead. */}
      <form onSubmit={handleSubmit} noValidate className="space-y-5">
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
              autoFocus
              // Usernames are ASCII, so an RTL field would put the caret on the wrong side of them.
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
              name="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={fa.auth.passwordPlaceholder}
              autoComplete="current-password"
              disabled={isSubmitting}
            />
          )}
        </Field>

        <Button type="submit" size="lg" fullWidth isLoading={isSubmitting}>
          {isSubmitting ? fa.auth.submittingLogin : fa.auth.submitLogin}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-ink-muted">
        {fa.auth.noAccount}{' '}
        <Link to={ROUTES.register} className="font-semibold text-accent-ink hover:underline">
          {fa.auth.goToRegister}
        </Link>
      </p>
    </div>
  )
}
