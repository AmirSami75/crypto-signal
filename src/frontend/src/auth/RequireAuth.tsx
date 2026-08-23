import { Navigate, useLocation } from 'react-router'
import { useAuth } from './AuthContext'
import { can, type PermissionName } from './permissions'
import { fa } from '../i18n/fa'
import { Alert } from '../components/ui/Alert'
import { Spinner } from '../components/ui/Spinner'
import { ROUTES } from '../routes'

/**
 * Gate for everything behind the dashboard shell.
 *
 * Three states, in order:
 *
 * 1. **Restoring.** The stored session has not been read yet, so neither "signed in" nor "signed
 *    out" is known. Rendering the redirect here would bounce a returning user to /login for one
 *    frame and lose the URL they typed.
 * 2. **No session.** Redirect to /login, recording where they were headed so the login form can
 *    return them there instead of dumping everyone on the overview page.
 * 3. **Password change pending.** `cs-admin` is seeded with `requiresPasswordChange: true`, and the
 *    server will keep saying so until it is done. Holding the user on that one screen is the only
 *    way the flag means anything — the alternative is a dashboard the account is not really
 *    supposed to be using yet.
 *
 * This is navigation, not enforcement. The server authorises every request independently; a user who
 * edited their way past this would find each call refused on its own merits.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { session, isRestoring } = useAuth()
  const location = useLocation()

  if (isRestoring) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!session) {
    // `state.from` is read back by LoginPage. `replace` keeps the unreachable URL out of history, so
    // the back button does not land on a redirect that fires again.
    return <Navigate to={ROUTES.login} replace state={{ from: location.pathname + location.search }} />
  }

  if (session.requiresPasswordChange && location.pathname !== ROUTES.changePassword) {
    return <Navigate to={ROUTES.changePassword} replace />
  }

  return <>{children}</>
}

/**
 * The inverse gate, for /login and /register: an already-signed-in user has no business on them, and
 * showing a login form to someone who is signed in reads as a bug.
 *
 * Sends them to the change-password screen instead of the dashboard when that is still pending, so
 * the two gates cannot bounce a session back and forth between them.
 */
export function RequireAnonymous({ children }: { children: React.ReactNode }) {
  const { session, isRestoring } = useAuth()

  if (isRestoring) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (session) {
    return <Navigate to={session.requiresPasswordChange ? ROUTES.changePassword : ROUTES.overview} replace />
  }

  return <>{children}</>
}

/**
 * Gate for a route that a permission controls.
 *
 * Renders a refusal rather than redirecting. A redirect would be a lie about what happened — the URL
 * exists and the user is signed in; they are simply not entitled to it — and bouncing them to the
 * overview page silently would look like a broken link. Superadmins pass automatically, which is
 * `can()`'s job: they arrive with an empty `permissions` array and an intersection test would lock
 * them out of everything.
 *
 * As with `RequireAuth`, this is navigation rather than enforcement. Every request is authorised
 * server-side on its own merits by `[CustomAuthorize]`, so nothing here is load-bearing for security —
 * it exists so the UI does not offer what the API will refuse.
 */
export function RequirePermission({
  permission,
  children,
}: {
  permission: PermissionName
  children: React.ReactNode
}) {
  const { session } = useAuth()

  if (!can(session, permission)) {
    return (
      <div className="mx-auto max-w-lg py-10">
        <Alert tone="error" title={fa.errors.forbidden} />
      </div>
    )
  }

  return <>{children}</>
}
