import type { Role, User } from '../lib/apiTypes'

/**
 * The rows the server refuses to let anyone touch.
 *
 * Three entities are seeded and then protected by name or type in the controllers: the `cs-admin`
 * account (`AuthGlobalVariables.DefaultUser`) and the `SuperAdmin` and `User` roles. Editing,
 * deleting, deactivating or resetting any of them comes back as a `LogicException` with a specific
 * Persian sentence.
 *
 * Recognising them client-side is not a security control — the server's refusal is, and it stands
 * whatever this file says. It is a courtesy: an operator on a fresh database is looking at exactly
 * one user and two roles, all three of them protected, and offering four buttons that can only ever
 * produce an error reads as a broken screen rather than as a rule. Showing why instead is honest.
 */

/** `AuthGlobalVariables.DefaultUser`. Guarded by *username* in every action that touches a user. */
const SYSTEM_USER_NAME = 'cs-admin'

/**
 * The seeded role types, as `RoleOutputDto` sends them.
 *
 * The server checks `RoleType.SuperAdmin or RoleType.User`, but the enum reaches the client already
 * resolved to its `[Display(Description)]` text — the wire carries `"مدیر سیستم"`, not `"SuperAdmin"`.
 * So the type test is against Persian strings, which is fragile enough on its own that the role's
 * `name` is checked alongside it: `Name` is what the seeder writes and it is not localised.
 */
const SYSTEM_ROLE_TYPES = ['مدیر سیستم', 'کاربر عادی']
const SYSTEM_ROLE_NAMES = ['SuperAdmin', 'User']

export function isSystemUser(user: Pick<User, 'userName'>): boolean {
  return user.userName === SYSTEM_USER_NAME
}

export function isSystemRole(role: Pick<Role, 'name' | 'type'>): boolean {
  if (role.type && SYSTEM_ROLE_TYPES.includes(role.type)) return true
  return SYSTEM_ROLE_NAMES.includes(role.name)
}
