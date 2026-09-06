/**
 * Route paths in one place.
 *
 * Separate from `router.tsx` so that guards, nav entries and redirects can reference a path without
 * importing the router itself — which would be a cycle, since the router imports the guards.
 */
export const ROUTES = {
  login: '/login',
  register: '/register',
  changePassword: '/change-password',

  overview: '/overview',

  signal: '/signal',
  bots: '/bots',
  /** Parameterised. Build a concrete path with {@link botDetailPath} rather than interpolating here. */
  botDetail: '/bots/:botId',
  botMonitor: '/bots/:botId/monitor',
  killSwitches: '/kill-switches',
  connections: '/connections',

  users: '/users',
  roles: '/roles',
  permissions: '/permissions',
  loginHistory: '/login-history',
  scanner: '/scanner',
  ml: '/ml',
  mlEngine: '/m-engine',
} as const

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES]

/** Route parameter name for {@link ROUTES.botDetail}, so the page's `useParams` cannot drift from it. */
export const BOT_ID_PARAM = 'botId'

/** Path to one bot's live monitor screen (same param, same builder discipline as {@link botDetailPath}). */
export function botMonitorPath(botId: string): string {
  return ROUTES.botMonitor.replace(`:${BOT_ID_PARAM}`, botId)
}

/**
 * Path to one bot's detail screen.
 *
 * Bot ids are GUIDs, so no escaping is needed — but going through a function means the `:botId`
 * segment is named in exactly one place. A hand-built `/bots/${id}` elsewhere would keep working right
 * up until the segment moves.
 */
export function botDetailPath(botId: string): string {
  return ROUTES.botDetail.replace(`:${BOT_ID_PARAM}`, botId)
}
