import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { api, setAuthFailureHandler, setAuthToken } from '../lib/api'
import type { ChangePasswordRequest, LoginRequest, RegisterRequest, SessionUser } from '../lib/apiTypes'

/**
 * Session state for the whole app.
 *
 * The token lives in `localStorage`, a deliberate choice with a real cost: any script that runs on
 * this origin can read it, so an XSS bug becomes a stolen session that outlives the tab. It buys
 * survival across a browser restart, which is what was asked for. Two things keep the blast radius
 * from being worse than it needs to be — nothing else sensitive is stored beside it, and the server
 * can revoke it out from under the client by rotating the security stamp (which logout, password
 * change, and account activation all do). If this is ever revisited, the upgrade path is a
 * short-lived token in memory plus a refresh cookie, which needs a server-side endpoint that does
 * not exist yet.
 */

const STORAGE_KEY = 'cs.session'

type AuthState = {
  session: SessionUser | null
  /** True until the stored session has been read and checked. Guards a redirect-before-restore flash. */
  isRestoring: boolean
}

type AuthContextValue = AuthState & {
  login: (payload: LoginRequest, signal?: AbortSignal) => Promise<SessionUser>
  register: (payload: RegisterRequest, signal?: AbortSignal) => Promise<void>
  changePassword: (payload: ChangePasswordRequest, signal?: AbortSignal) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

/**
 * Parses the server's `tokenExpiry` and returns whether it is still in the future.
 *
 * The server builds it from `DateTime.UtcNow`, so the serialised form carries a `Z`. A string with no
 * timezone marker at all would be read by `Date` as *local* time, which in a UTC+03:30 browser would
 * make a live token look 3.5 hours more valid than it is. Appending `Z` in that case costs nothing
 * and stops the check from depending on a serialiser setting elsewhere in the stack.
 */
function isExpiryInFuture(tokenExpiry: string): boolean {
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(tokenExpiry.trim())
  const parsed = new Date(hasZone ? tokenExpiry : `${tokenExpiry}Z`)
  if (Number.isNaN(parsed.getTime())) return false

  // A one-minute margin: a token about to expire mid-request is better treated as already gone than
  // spent on a call that will come back 401.
  return parsed.getTime() - Date.now() > 60_000
}

function isSessionShape(value: unknown): value is SessionUser {
  if (value === null || typeof value !== 'object') return false
  const candidate = value as Partial<SessionUser>
  return (
    typeof candidate.token === 'string' &&
    typeof candidate.userId === 'string' &&
    typeof candidate.userName === 'string' &&
    typeof candidate.tokenExpiry === 'string' &&
    typeof candidate.isSuperAdmin === 'boolean' &&
    Array.isArray(candidate.permissions) &&
    Array.isArray(candidate.roles)
  )
}

/**
 * Reads the stored session, returning null for anything unusable.
 *
 * Validated rather than trusted: `localStorage` is user-editable and survives deployments, so it can
 * hold a session written by an older build with different fields. A shape check here is the
 * difference between "signed out" and a crash inside a component reading `session.permissions` off
 * something that has none.
 */
function readStoredSession(): SessionUser | null {
  let raw: string | null
  try {
    raw = window.localStorage.getItem(STORAGE_KEY)
  } catch {
    // Storage can throw outright — Safari private mode, or a blocked-cookies setting.
    return null
  }
  if (!raw) return null

  try {
    const parsed: unknown = JSON.parse(raw)
    if (!isSessionShape(parsed)) return null
    if (!isExpiryInFuture(parsed.tokenExpiry)) return null
    return parsed
  } catch {
    return null
  }
}

function writeStoredSession(session: SessionUser | null): void {
  try {
    if (session) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
    else window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Nothing useful to do if storage is unavailable: the session still works for this tab, it just
    // will not survive a reload.
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  // Read synchronously on first render rather than in an effect. Doing it in an effect would render
  // one frame as signed-out, and `RequireAuth` would navigate to /login before the restore landed.
  const [session, setSession] = useState<SessionUser | null>(() => {
    const restored = readStoredSession()
    setAuthToken(restored?.token ?? null)
    return restored
  })
  const [isRestoring, setIsRestoring] = useState(true)

  // Lets the auth-failure handler clear a session without being re-registered on every change.
  const sessionRef = useRef(session)
  sessionRef.current = session

  const applySession = useCallback((next: SessionUser | null) => {
    setSession(next)
    setAuthToken(next?.token ?? null)
    writeStoredSession(next)
  }, [])

  useEffect(() => {
    // Any stored session was already validated against its expiry in the initialiser; this only
    // closes the restoring window so the router can start making decisions.
    setIsRestoring(false)
  }, [])

  useEffect(() => {
    // Fires only for a transport 401 — a token the server refused. An envelope-level `Unauthorized`
    // (a missing permission) deliberately does not reach here; see `ApiError.isAuthFailure`.
    setAuthFailureHandler(() => {
      if (sessionRef.current) applySession(null)
    })
    return () => setAuthFailureHandler(null)
  }, [applySession])

  /**
   * Keeps tabs in step. Signing out in one tab should not leave another showing a dashboard whose
   * every request now fails — `storage` fires only in the *other* tabs, which is exactly the ones
   * that need telling.
   */
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== STORAGE_KEY && event.key !== null) return
      const next = readStoredSession()
      setSession(next)
      setAuthToken(next?.token ?? null)
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const login = useCallback(
    async (payload: LoginRequest, signal?: AbortSignal) => {
      const next = await api.auth.login(payload, signal)
      applySession(next)
      return next
    },
    [applySession],
  )

  const register = useCallback(async (payload: RegisterRequest, signal?: AbortSignal) => {
    // Returns no token on purpose: the account is created inactive and cannot sign in until an
    // administrator activates it, so there is no session to establish here.
    await api.auth.register(payload, signal)
  }, [])

  const changePassword = useCallback(
    async (payload: ChangePasswordRequest, signal?: AbortSignal) => {
      await api.auth.changePassword(payload, signal)

      // The server rotated the security stamp, so the token just used is now dead. Clearing the
      // session is not a courtesy — keeping it would leave the app holding a token that fails every
      // subsequent request.
      applySession(null)
    },
    [applySession],
  )

  const logout = useCallback(async () => {
    try {
      await api.auth.logout()
    } catch {
      // The server-side call rotates the security stamp, which is worth attempting, but a failure
      // must not trap the user in a session they asked to leave. Clear locally regardless.
    }
    applySession(null)
  }, [applySession])

  const value = useMemo<AuthContextValue>(
    () => ({ session, isRestoring, login, register, changePassword, logout }),
    [session, isRestoring, login, register, changePassword, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
