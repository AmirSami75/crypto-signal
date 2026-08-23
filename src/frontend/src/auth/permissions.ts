import type { SessionUser } from '../lib/apiTypes'

/**
 * Permission names as the server mints them, from `[Permission]` attributes via `PermissionSeeder`.
 * Listed as constants so a typo is a compile error rather than a nav entry that silently never shows.
 *
 * These are the sixteen rows `GET /api/v1/permission` returns today. If the catalogue grows, this
 * list is the place to mirror it.
 */
export const PERMISSIONS = {
  userGet: 'User.Get',
  userCreate: 'User.Create',
  userUpdate: 'User.Update',
  userDelete: 'User.Delete',
  userResetPassword: 'User.ResetPassword',
  userActivate: 'User.AccountActivation',
  userDeactivate: 'User.AccountDeActivation',

  roleGet: 'Role.Get',
  roleCreate: 'Role.Create',
  roleUpdate: 'Role.Update',
  roleDelete: 'Role.Delete',

  permissionGet: 'Permission.Get',
  loginHistoryGet: 'LoginHistory.Get',

  mlGetModel: 'Ml.GetModel',
  mlGetCapabilities: 'Ml.GetCapabilities',
  mlPredictSignal: 'Ml.PredictSignal',
} as const

export type PermissionName = (typeof PERMISSIONS)[keyof typeof PERMISSIONS]

/**
 * Whether the session may use a given permission.
 *
 * The superadmin branch is the whole point of this function. `BaseAuthController` skips permission
 * collection entirely for a user holding a superadmin role, so `cs-admin` signs in with
 * `permissions: []` and `isSuperAdmin: true`. Anything that intersected the array directly would
 * conclude the most privileged account on the platform may do nothing — hiding every nav entry from
 * the only account that exists on a fresh database.
 *
 * This is a *rendering* decision only. It hides controls the user cannot use; it never grants
 * anything. The server re-checks every call through `CustomAuthorizeAttribute`, and a denial there
 * comes back as HTTP 200 with `statusCode: "Unauthorized"` — so a client that got this wrong would
 * produce a dead button, not an escalation.
 */
export function can(session: SessionUser | null, permission: PermissionName): boolean {
  if (!session) return false
  if (session.isSuperAdmin) return true
  return session.permissions.includes(permission)
}

/** True when the session holds at least one of the given permissions. */
export function canAny(session: SessionUser | null, permissions: PermissionName[]): boolean {
  if (!session) return false
  if (session.isSuperAdmin) return true
  return permissions.some((permission) => session.permissions.includes(permission))
}
