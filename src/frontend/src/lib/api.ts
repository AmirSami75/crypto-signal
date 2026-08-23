import { fa } from '../i18n/fa'
import type {
  ApiStatusCode,
  ApiStatusName,
  ChangePasswordRequest,
  DevErrorPayload,
  LoginHistoryEntry,
  LoginHistoryFilters,
  LoginRequest,
  PagedResult,
  PageQuery,
  PlatformInfo,
  Permission,
  Readiness,
  RawEnvelope,
  RegisterRequest,
  Role,
  RoleInput,
  SessionUser,
  TitleFilter,
  User,
  UserFilters,
  UserInput,
} from './apiTypes'

/**
 * The single place that talks to the API.
 *
 * Its whole reason for existing is that the API answers in six different shapes depending on which
 * layer produced the response. Each was confirmed against the running service:
 *
 * | Producer | Body | HTTP |
 * | --- | --- | --- |
 * | MVC success (`AddNewtonsoftJson` + `StringEnumConverter`) | `{data, isSuccess:true, statusCode:"Success", message}` | 200 |
 * | `ApiResultFilterAttribute` validation failure | `{isSuccess:false, statusCode:"BadRequest", message:"a \| b \| c"}` | 400 |
 * | `CustomAuthorizeAttribute` permission denial | `{isSuccess:false, statusCode:"Unauthorized", message}` | **200** |
 * | `UnifiedExceptionHandlerMiddleware` | `{IsSuccess:false, StatusCode:422, Message}` — PascalCase, numeric | 4xx/5xx |
 * | Rate limiter `OnRejected` | `{isSuccess:false, statusCode:429, message}` | 429 |
 * | JWT bearer `OnChallenge` | `{error:"unauthorized", code:"AuthenticationFailed"}` — no envelope | 401 |
 *
 * Two of those rows are traps a caller would otherwise fall into:
 *
 * 1. **A permission denial arrives as HTTP 200.** `response.ok` is therefore not a success test —
 *    `isSuccess` is. Nothing outside this file may branch on the HTTP status.
 * 2. **In Development the middleware replaces `Message` with a serialised dictionary**, so the real
 *    sentence is nested at `.Exception` with a full server `.StackTrace` beside it. Rendered as-is,
 *    a wrong password would print a .NET stack trace into the login form. `unwrapDevMessage()`
 *    exists to make sure that never reaches a component.
 *
 * The asymmetry is deliberately absorbed here rather than fixed on the server: the error envelope is
 * a published contract, and changing it is a breaking change well outside the scope of building
 * these screens. Worth revisiting on the server side later.
 */

/** Thrown for every failed call, whatever shape the failure arrived in. */
export class ApiError extends Error {
  /** The server's status code, normalised to a number. `0` when the request never landed. */
  readonly status: number

  /**
   * Individual validation messages, when the failure was a validation failure. The filter joins them
   * with `' | '` into one string; splitting them back apart lets a form list them as bullets instead
   * of as one run-on sentence.
   */
  readonly details: string[]

  /**
   * True only for a transport-level 401 — a token the server refused. This is the signal to end the
   * session, and it is deliberately *not* set for an envelope `statusCode: "Unauthorized"`, which
   * means "authenticated fine, but lacks this permission". Conflating the two would bounce a
   * perfectly valid session back to the login screen the first time a user opened a page they are
   * not entitled to.
   */
  readonly isAuthFailure: boolean

  constructor(message: string, status: number, details: string[] = [], isAuthFailure = false) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
    this.isAuthFailure = isAuthFailure
  }
}

/** Maps the enum's member names onto their numeric values, for the MVC spelling. */
const STATUS_BY_NAME: Record<ApiStatusName, ApiStatusCode> = {
  Success: 200,
  NoContent: 204,
  BadRequest: 400,
  Unauthorized: 401,
  Forbidden: 403,
  NotFound: 404,
  Conflict: 409,
  ValidationError: 422,
  ServerError: 500,
  ServiceUnavailable: 503,
}

const VALIDATION_SEPARATOR = ' | '

function toStatusNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number') return value
  if (typeof value === 'string') {
    const mapped = STATUS_BY_NAME[value as ApiStatusName]
    if (mapped !== undefined) return mapped

    // A numeric string, in case a future serialiser setting changes its mind about the enum.
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

/**
 * Pulls the human sentence out of a Development-mode error message, discarding the stack trace.
 * Outside Development `Message` is already the sentence and this returns it unchanged.
 */
function unwrapDevMessage(message: string): string {
  const trimmed = message.trim()
  if (!trimmed.startsWith('{')) return trimmed

  try {
    const parsed = JSON.parse(trimmed) as DevErrorPayload
    const inner = parsed.Exception?.trim()
    if (inner) return inner
  } catch {
    // Not JSON after all — a message that merely happens to begin with a brace. Fall through and
    // show it as written rather than swallowing it.
  }
  return trimmed
}

type Normalised = {
  ok: boolean
  status: number
  message: string
  details: string[]
  data: unknown
}

/** Folds any of the six response shapes into one. */
function normalise(body: unknown, httpStatus: number): Normalised {
  // A body that is not an object at all: an empty 204, an HTML error page from a proxy, a truncated
  // response. Fall back to the HTTP status, which is the only thing left to go on.
  if (body === null || typeof body !== 'object') {
    const ok = httpStatus >= 200 && httpStatus < 300
    return {
      ok,
      status: httpStatus,
      message: ok ? '' : statusMessage(httpStatus),
      details: [],
      data: body,
    }
  }

  const envelope = body as Record<string, unknown> & RawEnvelope

  // The JWT challenge, which has no envelope: `{error, code}` and nothing else. Detected by the
  // absence of both spellings of `isSuccess` rather than by the presence of `error`, so a future
  // envelope that happens to carry an `error` field is not mistaken for it.
  const hasEnvelope = 'isSuccess' in envelope || 'IsSuccess' in envelope
  if (!hasEnvelope && 'error' in envelope) {
    return {
      ok: false,
      status: httpStatus || 401,
      message: statusMessage(httpStatus || 401),
      details: [],
      data: undefined,
    }
  }

  const isSuccess = (envelope.isSuccess ?? envelope.IsSuccess) as boolean | undefined
  const rawStatus = envelope.statusCode ?? envelope.StatusCode
  const rawMessage = (envelope.message ?? envelope.Message) as string | null | undefined

  const status = toStatusNumber(rawStatus, httpStatus)

  // `isSuccess` is authoritative. It disagrees with the HTTP status on exactly one path — a
  // permission denial, which is HTTP 200 with `isSuccess: false` — and on that path the envelope is
  // right and the status line is not.
  const ok = isSuccess === true

  const message = typeof rawMessage === 'string' ? unwrapDevMessage(rawMessage) : ''

  // The validation filter joins messages with ' | '. Split only on failure: a success message would
  // never be a list, and a legitimate '|' inside prose is far likelier there.
  const details =
    !ok && message.includes(VALIDATION_SEPARATOR)
      ? message
          .split(VALIDATION_SEPARATOR)
          .map((part) => part.trim())
          .filter(Boolean)
      : []

  return {
    ok,
    status,
    message: message || (ok ? '' : statusMessage(status)),
    details,
    data: 'data' in envelope ? envelope.data : undefined,
  }
}

function statusMessage(status: number): string {
  return fa.errors.byStatus[status] ?? fa.errors.unexpected
}

/** Set by `AuthContext` so requests carry a bearer token without every caller passing one. */
let authToken: string | null = null

/**
 * Called by `AuthContext` when a transport 401 proves the stored token is dead, so the session can
 * be cleared from wherever the failure happened to surface.
 */
let onAuthFailure: (() => void) | null = null

export function setAuthToken(token: string | null): void {
  authToken = token
}

export function setAuthFailureHandler(handler: (() => void) | null): void {
  onAuthFailure = handler
}

/**
 * Coarse client hints recorded in the login-history row by `BaseAuthController`, which reads
 * `X-ClientOS` and `X-ClientBrowser` off the request.
 *
 * Parsed from the user-agent string, which is a guess and always has been — the values exist so an
 * audit row says something more useful than "unknown", not so anything can be decided from them.
 * `X-ClientIp` is deliberately not sent: a client-supplied address is trivially forged, and the
 * server can see the real one.
 */
function clientHints(): Record<string, string> {
  if (typeof navigator === 'undefined') return {}

  const ua = navigator.userAgent

  const os =
    /Windows NT/.test(ua) ? 'Windows'
    : /Android/.test(ua) ? 'Android'
    : /iPhone|iPad|iPod/.test(ua) ? 'iOS'
    : /Mac OS X/.test(ua) ? 'macOS'
    : /Linux/.test(ua) ? 'Linux'
    : 'Unknown'

  // Order matters: Edge and Chrome both claim to be Chrome, and Chrome claims to be Safari.
  const browser =
    /Edg\//.test(ua) ? 'Edge'
    : /OPR\//.test(ua) ? 'Opera'
    : /Firefox\//.test(ua) ? 'Firefox'
    : /Chrome\//.test(ua) ? 'Chrome'
    : /Safari\//.test(ua) ? 'Safari'
    : 'Unknown'

  return { 'X-ClientOS': os, 'X-ClientBrowser': browser }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  body?: unknown
  /** Adds the login-history hint headers. Only `POST /auth/login` reads them. */
  withClientHints?: boolean
  /** Skips the bearer header, for the anonymous endpoints. */
  anonymous?: boolean
  signal?: AbortSignal
}

/**
 * Issues one request and returns the envelope's `data`, or throws `ApiError`.
 *
 * Paths are relative (`/api/v1/...`), so Vite's dev proxy and the production nginx both route them
 * without the client knowing where the API lives. That is also what keeps the browser from ever
 * holding an absolute API address, let alone the Python service's.
 */
async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, withClientHints = false, anonymous = false, signal } = options

  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (!anonymous && authToken) headers.Authorization = `Bearer ${authToken}`
  if (withClientHints) Object.assign(headers, clientHints())

  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (error) {
    // An aborted request is the caller unmounting, not a failure worth reporting.
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(fa.errors.network, 0)
  }

  // Read as text first: an error page from a proxy, or an empty 204, is not JSON, and `.json()`
  // would throw over the top of the real status.
  const text = await response.text()
  let parsed: unknown = null
  if (text.length > 0) {
    try {
      parsed = JSON.parse(text)
    } catch {
      throw new ApiError(fa.errors.malformed, response.status)
    }
  }

  const result = normalise(parsed, response.status)

  if (!result.ok) {
    // Only the transport status can condemn the token. See `ApiError.isAuthFailure`.
    const isAuthFailure = response.status === 401
    if (isAuthFailure) onAuthFailure?.()
    throw new ApiError(result.message, result.status, result.details, isAuthFailure)
  }

  return result.data as T
}

/**
 * For the two endpoints that answer with a bare object rather than an `ApiResult`:
 * `GET /api/v1/platform` and `GET /health/ready`. Kept separate so `request()` does not have to
 * guess whether a body without `isSuccess` is an unwrapped payload or a malformed envelope.
 */
async function requestUnwrapped<T>(
  path: string,
  signal?: AbortSignal,
  /**
   * Statuses whose *body* is still the answer rather than an error to report.
   *
   * `/health/ready` answers **503** whenever a dependency is down, and that body is the single most
   * useful response the endpoint produces — it names which dependency. Treating the status alone as
   * the outcome would leave the overview page able to say only "something is wrong".
   */
  bodyBearingStatuses: readonly number[] = [],
): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, { headers: { Accept: 'application/json' }, signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(fa.errors.network, 0)
  }

  if (!response.ok && !bodyBearingStatuses.includes(response.status))
    throw new ApiError(statusMessage(response.status), response.status)

  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError(fa.errors.malformed, response.status)
  }
}

/**
 * Builds a query string from a filter object, dropping anything the user has not actually set.
 *
 * The omission is the point. Every search DTO field is nullable and the server's filter builder
 * skips a null, but an *empty string* is not null — sending `?UserName=` makes it filter on
 * `Contains("")`, and sending `?IsActive=` fails to bind to `bool?` and 400s the whole listing. So a
 * cleared text box has to disappear from the URL rather than travel as a blank.
 *
 * `false` and `0` are kept: they are real filter values, which is why the test is against `''`,
 * `null` and `undefined` one at a time instead of a truthiness check.
 */
function queryString(filters: Record<string, string | number | boolean | null | undefined>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

/**
 * `/{page}/{pageSize}/{desc}` — the paged shape every listing controller shares.
 *
 * All three are route *segments*, not query parameters, and none of them is optional: omitting
 * `desc` does not fall back to a default, it fails to match the route and 404s. Defaulted to
 * newest-first because every one of these tables is read that way.
 */
function pagedPath(resource: string, { page, pageSize, desc = true }: PageQuery): string {
  return `${resource}/${page}/${pageSize}/${desc}`
}

export const api = {
  auth: {
    login: (payload: LoginRequest, signal?: AbortSignal) =>
      request<SessionUser>('/api/v1/auth/login', {
        method: 'POST',
        body: payload,
        anonymous: true,
        withClientHints: true,
        signal,
      }),

    /** Returns nothing: registration deliberately issues no token. */
    register: (payload: RegisterRequest, signal?: AbortSignal) =>
      request<void>('/api/v1/auth/register', {
        method: 'POST',
        body: payload,
        anonymous: true,
        signal,
      }),

    logout: (signal?: AbortSignal) =>
      request<void>('/api/v1/auth/logout', { method: 'POST', signal }),

    /**
     * Rotates the security stamp server-side, which invalidates the token currently in hand — so a
     * successful call always ends the session and the user signs in again with the new password.
     */
    changePassword: (payload: ChangePasswordRequest, signal?: AbortSignal) =>
      request<void>('/api/v1/auth/change-password', { method: 'PUT', body: payload, signal }),

    validateSession: (signal?: AbortSignal) =>
      request<{ ok: boolean }>('/api/v1/auth/session-validate', { signal }),
  },

  users: {
    paged: (query: PageQuery, filters: UserFilters = {}, signal?: AbortSignal) =>
      request<PagedResult<User>>(`${pagedPath('/api/v1/user', query)}${queryString(filters)}`, { signal }),

    /** Every user, unpaged. Used to populate the parent-account picker, not to render a table. */
    list: (signal?: AbortSignal) => request<User[]>('/api/v1/user', { signal }),

    byId: (id: string, signal?: AbortSignal) => request<User>(`/api/v1/user/${id}`, { signal }),

    /**
     * The new account is born active with the server's default password and a forced-change flag —
     * the payload carries no password field at all, so there is nothing to communicate to the new
     * user beyond "sign in with the default and change it".
     */
    create: (payload: UserInput, signal?: AbortSignal) =>
      request<User>('/api/v1/user', { method: 'POST', body: payload, signal }),

    /**
     * The id travels in the path *and* the body, because `CrudController.Update` is
     * `[HttpPut("{id}")]` and the route value is what it looks the row up by — `entity.Id = id`
     * overwrites whatever the payload claimed. Putting to the collection path instead does not fall
     * back to the body's id; it fails to match the route and comes back 405.
     */
    update: (payload: UserInput & { id: string }, signal?: AbortSignal) =>
      request<User>(`/api/v1/user/${payload.id}`, { method: 'PUT', body: payload, signal }),

    /** Soft delete. Refused for `cs-admin`. */
    remove: (id: string, signal?: AbortSignal) =>
      request<void>(`/api/v1/user/${id}`, { method: 'DELETE', signal }),

    // The next three are PUTs whose only input is a query parameter — no body. Sending one as JSON
    // instead would bind `userId` to the default and act on a zero guid.
    activate: (userId: string, signal?: AbortSignal) =>
      request<void>(`/api/v1/user/account-activation${queryString({ userId })}`, { method: 'PUT', signal }),

    deactivate: (userId: string, signal?: AbortSignal) =>
      request<void>(`/api/v1/user/account-de-activation${queryString({ userId })}`, { method: 'PUT', signal }),

    /** Back to the default password, forced-change set, lockout and failure count cleared. */
    resetPassword: (userId: string, signal?: AbortSignal) =>
      request<void>(`/api/v1/user/reset-password${queryString({ userId })}`, { method: 'PUT', signal }),
  },

  roles: {
    paged: (query: PageQuery, filters: TitleFilter = {}, signal?: AbortSignal) =>
      request<PagedResult<Role>>(`${pagedPath('/api/v1/role', query)}${queryString(filters)}`, { signal }),

    /** Unpaged, for the role checkboxes on the user form. */
    list: (signal?: AbortSignal) => request<Role[]>('/api/v1/role', { signal }),

    byId: (id: string, signal?: AbortSignal) => request<Role>(`/api/v1/role/${id}`, { signal }),

    create: (payload: RoleInput, signal?: AbortSignal) =>
      request<Role>('/api/v1/role', { method: 'POST', body: payload, signal }),

    /**
     * Replaces the permission set wholesale — the server drops every `RolePermission` row for the
     * role and re-adds from the payload. The id is a route segment here for the same reason as on
     * the user endpoint; see the note there.
     */
    update: (payload: RoleInput & { id: string }, signal?: AbortSignal) =>
      request<Role>(`/api/v1/role/${payload.id}`, { method: 'PUT', body: payload, signal }),

    /** Refused for the two seeded roles, `SuperAdmin` and `User`. */
    remove: (id: string, signal?: AbortSignal) =>
      request<void>(`/api/v1/role/${id}`, { method: 'DELETE', signal }),
  },

  permissions: {
    list: (signal?: AbortSignal) => request<Permission[]>('/api/v1/permission', { signal }),

    paged: (query: PageQuery, filters: TitleFilter = {}, signal?: AbortSignal) =>
      request<PagedResult<Permission>>(
        `${pagedPath('/api/v1/permission', query)}${queryString(filters)}`,
        { signal },
      ),
  },

  loginHistory: {
    // Kebab-cased by the route transformer: `/login-history`, not `/loginhistory`. The wrong spelling
    // 404s with an HTML body, which surfaces as a parse failure rather than as "no such route".
    paged: (query: PageQuery, filters: LoginHistoryFilters = {}, signal?: AbortSignal) =>
      request<PagedResult<LoginHistoryEntry>>(
        `${pagedPath('/api/v1/login-history', query)}${queryString(filters)}`,
        { signal },
      ),
  },

  platform: {
    info: (signal?: AbortSignal) => requestUnwrapped<PlatformInfo>('/api/v1/platform', signal),
    // 503 is a normal, informative answer here: degraded, with the failing dependency named.
    readiness: (signal?: AbortSignal) => requestUnwrapped<Readiness>('/health/ready', signal, [503]),
  },
}

/** Turns any thrown value into a sentence fit to render. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message || fa.errors.unexpected
  if (error instanceof Error && error.message) return error.message
  return fa.errors.unexpected
}

/** The individual validation messages behind a failure, if it carried any. */
export function errorDetails(error: unknown): string[] {
  return error instanceof ApiError ? error.details : []
}
