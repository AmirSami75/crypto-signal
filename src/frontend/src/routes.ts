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
  users: '/users',
  roles: '/roles',
  permissions: '/permissions',
  loginHistory: '/login-history',
  ml: '/ml',
} as const

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES]
