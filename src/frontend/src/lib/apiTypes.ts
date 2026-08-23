/**
 * Types mirroring the API's wire contract.
 *
 * These describe what the API *sends*, not what the app would prefer to receive. The reshaping into
 * something uniform happens in `api.ts`; keeping the raw shapes named and separate is what makes
 * that normalisation reviewable — each awkward variant below corresponds to one branch there.
 */

/** `ApiResultStatusCode` on the server. Numeric, because it doubles as the HTTP status. */
export type ApiStatusCode = 200 | 204 | 400 | 401 | 403 | 404 | 409 | 422 | 429 | 500 | 503

/**
 * The same enum as the server sometimes spells it: as a member *name*, because MVC serialises with
 * `StringEnumConverter` while the exception middleware and the rate limiter emit the number.
 */
export type ApiStatusName =
  | 'Success'
  | 'NoContent'
  | 'BadRequest'
  | 'Unauthorized'
  | 'Forbidden'
  | 'NotFound'
  | 'Conflict'
  | 'ValidationError'
  | 'ServerError'
  | 'ServiceUnavailable'

/**
 * Every envelope the API is known to produce, as a union. Six shapes were confirmed against the
 * running service; see `normalise()` in `api.ts` for where each one comes from and what it means.
 */
export type RawEnvelope =
  /** MVC, success or a filter-level validation failure: camelCase keys, enum as a name. */
  | {
      data?: unknown
      isSuccess?: boolean
      statusCode?: ApiStatusName | ApiStatusCode
      message?: string | null
    }
  /** `UnifiedExceptionHandlerMiddleware`: PascalCase keys, enum as a number. */
  | {
      IsSuccess?: boolean
      StatusCode?: ApiStatusCode
      Message?: string | null
    }
  /** The JWT bearer `OnChallenge` handler: no envelope at all. */
  | { error?: string; code?: string }

/**
 * The shape the middleware puts inside `Message` when the environment is Development: the real text
 * is nested under `Exception`, with a full server stack trace alongside it.
 */
export type DevErrorPayload = {
  Exception?: string
  StackTrace?: string
}

/**
 * Paged listing envelope.
 *
 * Both counts are sent and they mean different things: `totalRecords` is the size of the whole
 * filtered set and is what the pager divides, while `count` is how many rows this particular page
 * carries. Reading `count` as the total shows "1 record" on a 62-row table, which is why they are
 * named apart here rather than collapsed into one field.
 */
export type PagedResult<T> = {
  totalRecords: number
  items: T[]
  pageNumber: number
  pageSize: number
  count: number
}

/**
 * Audit trail on every `BaseOutputDto`, and an unusual shape worth naming.
 *
 * `creationDate` is *not* a date: it is the Jalali date and the acting user joined by a space —
 * `"1405/06/01 System Administrator"` — because the server interpolates both into one string. The
 * date is the first whitespace-delimited token; the remainder is a display name that may itself
 * contain spaces. `jalaliDate()` and `auditActor()` in `lib/format.ts` do that split in one place.
 *
 * When a row has never been updated the modification pair is the literal `" "`: the interpolation
 * runs over two nulls and yields a lone separator, not null. Anything rendering these has to treat
 * whitespace-only as absent — a bare `?? '—'` will happily print a blank cell.
 */
export type AuditFields = {
  creationDate: string
  creationTime: string
  modificationDate: string | null
  modificationTime: string | null
  userCreatedName: string | null
  userLastUpdateName: string | null
}

/** A permission as the catalogue returns it — `name` is the string `can()` matches against. */
export type Permission = {
  id: string
  name: string
  title: string
} & AuditFields

/** `RoleType`, already resolved to its Persian display text by the server rather than sent as a name. */
export type RoleTypeLabel = 'مدیر سیستم' | 'کاربر عادی' | 'کاربر'

/**
 * A role. `permissions` is the full nested catalogue subset on every *role* endpoint (list, paged,
 * by-id) — but see `Role` inside `User`, where the projection leaves it null.
 */
export type Role = {
  id: string
  name: string
  title: string
  type: RoleTypeLabel | string | null
  permissions: Permission[] | null
} & AuditFields

/**
 * A role as it appears *nested inside a user*, which is a strictly smaller shape.
 *
 * `UserOutputDto` projects only three columns out of the join, so `type` and `permissions` come back
 * null and the audit strings come back `" "` — the row was never actually mapped through
 * `RoleOutputDto`'s enrichment pass. Reading `user.roles[0].permissions.length` therefore throws.
 * Fetch the role by id when its permissions are needed.
 */
export type RoleRef = Pick<Role, 'id' | 'name' | 'title'>

/** Create/update payload for a role. `permissions` carries ids only; the server rejects an empty list. */
export type RoleInput = {
  id?: string
  name: string
  title: string
  permissions: Array<{ id: string }>
}

/** `UserType`, sent and accepted as the enum *name* — the `[Display]` text happens to be Latin too. */
export type UserTypeName = 'Administrator' | 'Trader' | 'Analyst' | 'Viewer'

export type User = {
  id: string
  fullName: string
  userName: string
  email: string | null
  phone: string | null
  mobile: string | null
  address: string | null
  personelCode: string | null
  isActive: boolean
  isLocked: boolean
  parentId: string | null
  /** Resolved server-side, so the table can name the parent without a second fetch. */
  parentName: string | null
  userType: UserTypeName | null
  /** Partial: ids and names only. See `RoleRef`. */
  roles: RoleRef[] | null
} & AuditFields

/**
 * Create/update payload for a user.
 *
 * There is no password field on purpose — the server hashes `AuthGlobalVariables.DefaultPassword`
 * for a new account and flags it for a forced change, so the operator never chooses one. `roles`
 * must be non-empty or `BaseUserInputDto.Validate` rejects the whole payload.
 */
export type UserInput = {
  id?: string
  fullName: string
  userName: string
  email?: string | null
  phone?: string | null
  mobile?: string | null
  address?: string | null
  personelCode?: string | null
  parentId?: string | null
  userType?: UserTypeName | null
  roles: Array<{ id: string }>
}

/**
 * One sign-in attempt. `status` is the `LoginStatus` enum name, and `dateTime` is a full Jalali
 * timestamp (`"1405/06/01 11:41:43"`) — unlike `creationDate`, no actor name is appended to it.
 *
 * The endpoint returns *every* user's attempts, not the caller's; the screen labels it accordingly.
 */
export type LoginHistoryEntry = {
  id: string
  ip: string | null
  userAgent: string | null
  dateTime: string
  status: 'Success' | 'Error' | string
} & AuditFields

/**
 * Query filters for the paged user listing.
 *
 * Keys are PascalCase to match the OpenAPI spec exactly. ASP.NET binds query strings
 * case-insensitively so camelCase would also work today, but matching the published contract keeps
 * the client honest if that ever tightens.
 */
export type UserFilters = {
  UserName?: string
  FullName?: string
  PersonelCode?: string
  Mobile?: string
  UserType?: UserTypeName | ''
  /** Tri-state: `undefined` means "either", not "false". */
  IsActive?: boolean
  IsLocked?: boolean
}

/** Both the role and the permission listings filter on the same single field. */
export type TitleFilter = { Title?: string }

export type LoginHistoryFilters = { IP?: string }

/** Path segments shared by every paged endpoint: `/{page}/{pageSize}/{desc}`. */
export type PageQuery = {
  page: number
  pageSize: number
  /** Newest-first when true. Applies to the entity's creation order. */
  desc?: boolean
}

/**
 * The authenticated session, as `POST /api/v1/auth/login` returns it in `data`.
 *
 * `permissions` is empty for a superadmin: the server skips permission collection entirely when the
 * user holds a superadmin role, so an empty array means "everything" there and "nothing" otherwise.
 * Never read it without checking `isSuperAdmin` first — `can()` in `auth/permissions.ts` exists so
 * that check happens in exactly one place.
 */
export type SessionUser = {
  userId: string
  userName: string
  fullName: string
  token: string
  /** ISO-8601 UTC instant. Compared against the clock on load to drop a stale session. */
  tokenExpiry: string
  isSuperAdmin: boolean
  isParent: boolean
  requiresPasswordChange: boolean
  roles: string[]
  permissions: string[]
  userType: string | null
}

export type LoginRequest = {
  userName: string
  password: string
}

export type RegisterRequest = {
  fullName: string
  userName: string
  password: string
  confirmPassword: string
  email?: string
  mobile?: string
}

export type ChangePasswordRequest = {
  currentPass: string
  newPass: string
  confirmNewPass: string
}

/** `GET /api/v1/platform`. Top-level, not wrapped in an `ApiResult`. */
export type PlatformInfo = {
  operatingMode: string
  executionPolicy: string
}

/**
 * `GET /health/ready`. Top-level, not wrapped in an `ApiResult`.
 *
 * Serialised by `Results.Json`, so camelCase from System.Text.Json's web defaults — not by the
 * Newtonsoft pipeline the MVC controllers use. Answers 200 when `status` is `"healthy"` and **503**
 * when it is `"degraded"`; both bodies are shaped the same, which is why the client reads the 503 one
 * instead of discarding it.
 */
export type Readiness = {
  service: string
  status: string
  timestamp: string
  /** Absent rather than empty when the report carries no dependency detail. */
  dependencies?: Array<{ name: string; status: string; detail?: string | null }> | null
}
