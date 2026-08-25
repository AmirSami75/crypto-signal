import type { SessionUser } from '../lib/apiTypes'

/**
 * Permission names as the server mints them, from `[Permission]` attributes via `PermissionSeeder`.
 * Listed as constants so a typo is a compile error rather than a nav entry that silently never shows.
 *
 * These are the rows `GET /api/v1/permission` returns today. If the catalogue grows, this list is the
 * place to mirror it.
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

  // Asking the engine for a trade is a different privilege from inspecting the engine, which is why
  // this is `Signal.*` and not a third `Ml.*` entry. It authorizes a *question*: the endpoint behind
  // it places no order, and no endpoint on the platform does.
  signalGet: 'Signal.Get',

  botGet: 'Bot.Get',
  botGetById: 'Bot.GetById',
  botCreate: 'Bot.Create',
  botUpdate: 'Bot.Update',
  botDelete: 'Bot.Delete',

  // Separate from create/update on purpose: authoring a bot's configuration and turning it loose on a
  // venue are different acts, and an operator may reasonably hold one without the other.
  botStart: 'Bot.Start',
  botPause: 'Bot.Pause',
  botStop: 'Bot.Stop',

  botHistoryGetDecisions: 'BotHistory.GetDecisions',
  botHistoryGetOrders: 'BotHistory.GetOrders',
  botHistoryGetPositions: 'BotHistory.GetPositions',
  botHistoryGetAudit: 'BotHistory.GetAudit',

  exchangeConnectionGet: 'ExchangeConnection.Get',
  exchangeConnectionCreate: 'ExchangeConnection.Create',
  exchangeConnectionUpdate: 'ExchangeConnection.Update',
  exchangeConnectionDelete: 'ExchangeConnection.Delete',

  killSwitchGet: 'KillSwitch.Get',
  killSwitchEngage: 'KillSwitch.Engage',
  killSwitchDisengage: 'KillSwitch.Disengage',
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
