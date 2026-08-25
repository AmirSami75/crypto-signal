import { fa } from '../i18n/fa'
import type { Permission } from './apiTypes'

/**
 * Grouping for the permission catalogue.
 *
 * Permission names are `Resource.Action` — `User.Get`, `Role.Delete`, `Bot.Start` — because
 * `PermissionSeeder` builds each one from a controller's `[ControllerInfo]` name and its `[Permission]`
 * action. That prefix is the only structure the catalogue has, and it is the structure a person
 * reading it expects: thirty-odd rows in a flat alphabetical list is a wall, while nine labelled
 * groups of two to five is a picker you can use.
 *
 * Trading resources come first because they are the ones an operator grants and revokes; the auth
 * resources are set up once. `Bot.Start` and `KillSwitch.Engage` are the two rows most worth finding
 * quickly, and burying them under four sections of user administration is how a grant gets made by
 * scrolling rather than by reading.
 *
 * The group order is fixed here rather than taken from the response. `GET /api/v1/permission` orders
 * by creation date descending, so today the list happens to start with `Role.*` and the order would
 * change the moment a permission is added or the seeder runs against a fresh database. A picker whose
 * sections move between deployments is one people learn to distrust.
 */

/** Group order, most-used first. Anything the server sends that is not listed sorts to the end. */
const GROUP_ORDER = [
  'Bot',
  'BotHistory',
  'Signal',
  'KillSwitch',
  'Ml',
  'User',
  'Role',
  'Permission',
  'LoginHistory',
] as const

/** The resource half of a permission name. Returns the whole name when there is no dot to split on. */
export function permissionResource(name: string): string {
  const dot = name.indexOf('.')
  return dot === -1 ? name : name.slice(0, dot)
}

/**
 * Persian label for a resource prefix, falling back to the prefix itself.
 *
 * The fallback matters: the catalogue grows whenever a controller gains a `[Permission]` action, and a
 * new resource would otherwise land in a group with no heading at all. Showing `Order` untranslated is
 * a missing translation; showing an unlabelled group is a broken screen.
 */
export function permissionGroupTitle(resource: string): string {
  return fa.permissions.groups[resource] ?? resource
}

export type PermissionGroup = {
  resource: string
  title: string
  permissions: Permission[]
}

export function groupPermissions(permissions: Permission[]): PermissionGroup[] {
  const byResource = new Map<string, Permission[]>()

  for (const permission of permissions) {
    const resource = permissionResource(permission.name)
    const bucket = byResource.get(resource)
    if (bucket) bucket.push(permission)
    else byResource.set(resource, [permission])
  }

  const rank = (resource: string) => {
    const index = GROUP_ORDER.indexOf(resource as (typeof GROUP_ORDER)[number])
    return index === -1 ? GROUP_ORDER.length : index
  }

  return Array.from(byResource, ([resource, items]) => ({
    resource,
    title: permissionGroupTitle(resource),
    // Within a group, by name: `User.AccountActivation` before `User.Get` before `User.Update`. The
    // server's own order is creation order, which reads as random.
    permissions: [...items].sort((a, b) => a.name.localeCompare(b.name)),
  })).sort((a, b) => rank(a.resource) - rank(b.resource) || a.resource.localeCompare(b.resource))
}
