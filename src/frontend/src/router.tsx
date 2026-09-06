import { createBrowserRouter, Navigate } from 'react-router'
import { fa } from './i18n/fa'
import { PERMISSIONS } from './auth/permissions'
import { RequireAnonymous, RequireAuth, RequirePermission } from './auth/RequireAuth'
import { AuthLayout } from './layouts/AuthLayout'
import { DashboardLayout } from './layouts/DashboardLayout'
import { BotsPage } from './pages/BotsPage'
import { BotDetailPage } from './pages/BotDetailPage'
import { BotMonitorPage } from './pages/BotMonitorPage'
import { ChangePasswordPage } from './pages/ChangePasswordPage'
import { ConnectionsPage } from './pages/ConnectionsPage'
import { KillSwitchesPage } from './pages/KillSwitchesPage'
import { LoginHistoryPage } from './pages/LoginHistoryPage'
import { MlEnginePage } from './pages/MlEnginePage'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { OverviewPage } from './pages/OverviewPage'
import { PermissionsPage } from './pages/PermissionsPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { RegisterPage } from './pages/RegisterPage'
import { ScannerPage } from './pages/ScannerPage'
import { RolesPage } from './pages/RolesPage'
import { SignalPage } from './pages/SignalPage'
import { UsersPage } from './pages/UsersPage'
import { ROUTES } from './routes'

/**
 * The route tree.
 *
 * Four groups, each with a different gate — which is why they are four layout routes rather than one:
 *
 * 1. **Anonymous, in the auth shell.** Login and registration, behind `RequireAnonymous` so a
 *    signed-in user is not shown a login form.
 * 2. **Change password, in the auth shell, ungated here.** It is the one screen that gates itself; see
 *    the note in `ChangePasswordPage` — a successful change destroys the session on purpose, and the
 *    shared guard would redirect out from under the confirmation. It sits in the auth shell rather
 *    than the dashboard for the same reason: it ends the session, so dashboard chrome around it would
 *    promise continuity it cannot deliver.
 * 3. **Authenticated, in the dashboard shell.** `RequireAuth` also holds an account with
 *    `requiresPasswordChange` on group 2 until it is done.
 * 4. **Bare.** The root redirect and the 404, which belong to no shell.
 *
 * The permission wrappers mirror the sidebar's `can()` filtering, so typing a URL reaches the same
 * answer as looking for the link. Both are conveniences: `[CustomAuthorize]` on the server is what
 * actually decides.
 */
export const router = createBrowserRouter([
  {
    element: (
      <RequireAnonymous>
        <AuthLayout />
      </RequireAnonymous>
    ),
    children: [
      { path: ROUTES.login, element: <LoginPage /> },
      { path: ROUTES.register, element: <RegisterPage /> },
    ],
  },

  {
    element: <AuthLayout />,
    children: [{ path: ROUTES.changePassword, element: <ChangePasswordPage /> }],
  },

  {
    element: (
      <RequireAuth>
        <DashboardLayout />
      </RequireAuth>
    ),
    children: [
      { path: ROUTES.overview, element: <OverviewPage /> },
      {
        path: ROUTES.signal,
        element: (
          <RequirePermission permission={PERMISSIONS.signalGet}>
            <SignalPage />
          </RequirePermission>
        ),
      },
      {
        path: ROUTES.bots,
        element: (
          <RequirePermission permission={PERMISSIONS.botGet}>
            <BotsPage />
          </RequirePermission>
        ),
      },
      {
        path: ROUTES.botDetail,
        element: (
          <RequirePermission permission={PERMISSIONS.botGetById}>
            <BotDetailPage />
          </RequirePermission>
        ),
      },
      {
        path: ROUTES.botMonitor,
        element: (
          <RequirePermission permission={PERMISSIONS.botGetById}>
            <BotMonitorPage />
          </RequirePermission>
        ),
      },
      {
        path: ROUTES.killSwitches,
        element: (
          <RequirePermission permission={PERMISSIONS.killSwitchGet}>
            <KillSwitchesPage />
          </RequirePermission>
        ),
      },
      {
        path: ROUTES.connections,
        element: (
          <RequirePermission permission={PERMISSIONS.exchangeConnectionGet}>
            <ConnectionsPage />
          </RequirePermission>
        ),
      },
      {
        path: ROUTES.scanner,
        element: (
          <RequirePermission permission={PERMISSIONS.scannerGet}>
            <ScannerPage />
          </RequirePermission>
        ),
      },
      {
        path: ROUTES.mlEngine,
        element: (
          <RequirePermission permission={PERMISSIONS.mlGetModel}>
            <MlEnginePage />
          </RequirePermission>
        ),
      },
      {
        path: ROUTES.users,
        element: (
          <RequirePermission permission={PERMISSIONS.userGet}>
            <UsersPage />
          </RequirePermission>
        ),
      },
      {
        path: ROUTES.roles,
        element: (
          <RequirePermission permission={PERMISSIONS.roleGet}>
            <RolesPage />
          </RequirePermission>
        ),
      },
      {
        path: ROUTES.permissions,
        element: (
          <RequirePermission permission={PERMISSIONS.permissionGet}>
            <PermissionsPage />
          </RequirePermission>
        ),
      },
      {
        path: ROUTES.loginHistory,
        element: (
          <RequirePermission permission={PERMISSIONS.loginHistoryGet}>
            <LoginHistoryPage />
          </RequirePermission>
        ),
      },
    ],
  },

  // `replace` so the back button does not land on the redirect and fire it again.
  { path: '/', element: <Navigate to={ROUTES.overview} replace /> },
  { path: '*', element: <NotFoundPage /> },
])
