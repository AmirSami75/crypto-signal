import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { fa } from '../i18n/fa'
import { useAuth } from '../auth/AuthContext'
import { can, PERMISSIONS, type PermissionName } from '../auth/permissions'
import { usePlatform } from '../lib/usePlatform'
import { Badge, StatusDot } from '../components/ui/Badge'
import { IconButton } from '../components/ui/IconButton'
import { BrandMark } from '../components/BrandMark'
import { ThemeToggle } from '../components/ThemeToggle'
import { ROUTES } from '../routes'

/**
 * Authenticated chrome: a sidebar pinned to the **right** (the leading edge in RTL), a slim header
 * band, and the routed page in between.
 *
 * Placement is done with logical properties throughout — `border-e`, `ms-*`, `start-0` — so the
 * mirror comes from `dir="rtl"` on <html> rather than from a pile of `rtl:` overrides. Set the
 * document to LTR and this same markup lays out correctly with the sidebar on the left.
 *
 * The sidebar is the **first** grid column, because grid columns are ordered along the inline axis:
 * in RTL column one is the rightmost. (Putting it second and reaching for `order-last` does the
 * opposite of what it reads like — that lands the sidebar on the left.)
 *
 * Depth comes from hairlines and whitespace, not shadows: the sidebar, the header and the page share
 * one `--line` and one continuous band height, so the sidebar's brand row and the header sit on the
 * same rule across the full width. `--app-header-height` is what keeps that promise — the only thing
 * three separate elements agree on by construction rather than by coincidence.
 *
 * Under `lg` the sidebar becomes an overlay drawer. It slides from the same edge it occupies on wide
 * screens — the one the hamburger sits on — is dismissible by Escape, by the scrim or by its own
 * close button, and closes on navigation: a drawer left open over the page the user just asked for is
 * the standard bug here.
 */

type NavEntry = {
  to: string
  label: string
  icon: React.ReactNode
  /** Omitted for entries everyone may see. */
  permission?: PermissionName
}

export function DashboardLayout() {
  const { session, logout } = useAuth()
  const { data: platform } = usePlatform()
  const location = useLocation()
  const navigate = useNavigate()

  const [isDrawerOpen, setIsDrawerOpen] = useState(false)
  const [isLoggingOut, setIsLoggingOut] = useState(false)

  // Safety net for navigation the drawer did not start — a guard bouncing the user elsewhere, say.
  // It deliberately is not the whole story: an effect keyed on the pathname does not re-run when the
  // pathname is already what it was, which is precisely a tap on the entry for the current page — the
  // highlighted one, and so the likely tap. That close is wired to the link itself.
  useEffect(() => {
    setIsDrawerOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!isDrawerOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsDrawerOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isDrawerOpen])

  const mode = platform?.operatingMode ?? 'PAPER'
  const isPaper = mode.toUpperCase() === 'PAPER'

  const mainNav: NavEntry[] = [
    { to: ROUTES.overview, label: fa.nav.overview, icon: <GridIcon /> },
    { to: ROUTES.signal, label: fa.nav.signal, icon: <PulseIcon />, permission: PERMISSIONS.signalGet },
    { to: ROUTES.bots, label: fa.nav.bots, icon: <BotIcon />, permission: PERMISSIONS.botGet },
    {
      to: ROUTES.killSwitches,
      label: fa.nav.killSwitches,
      icon: <StopIcon />,
      permission: PERMISSIONS.killSwitchGet,
    },
    { to: ROUTES.connections, label: fa.nav.connections, icon: <ChipIcon />, permission: PERMISSIONS.exchangeConnectionGet },
    { to: ROUTES.ml, label: fa.nav.ml, icon: <ChipIcon />, permission: PERMISSIONS.mlGetModel },
  ]

  const adminNav: NavEntry[] = [
    { to: ROUTES.users, label: fa.nav.users, icon: <UsersIcon />, permission: PERMISSIONS.userGet },
    { to: ROUTES.roles, label: fa.nav.roles, icon: <ShieldIcon />, permission: PERMISSIONS.roleGet },
    { to: ROUTES.permissions, label: fa.nav.permissions, icon: <KeyIcon />, permission: PERMISSIONS.permissionGet },
    {
      to: ROUTES.loginHistory,
      label: fa.nav.loginHistory,
      icon: <ClockIcon />,
      permission: PERMISSIONS.loginHistoryGet,
    },
  ]

  // `can()` returns true for everything when isSuperAdmin, which is what makes the seeded cs-admin —
  // who arrives with an empty permissions array — see the full menu rather than none of it.
  const visible = (entries: NavEntry[]) =>
    entries.filter((entry) => !entry.permission || can(session, entry.permission))

  const visibleMain = visible(mainNav)
  const visibleAdmin = visible(adminNav)

  // The header names the section the user is in. Taken from the nav table rather than a second
  // pathname→title map, so a renamed entry cannot disagree with its own heading. Gated routes that
  // refuse the visit still resolve here, which is right: the refusal is *about* that section.
  const currentSection = [...mainNav, ...adminNav].find((entry) => entry.to === location.pathname)

  const handleLogout = async () => {
    setIsLoggingOut(true)
    await logout()
    navigate(ROUTES.login, { replace: true })
  }

  /** Shared by the persistent sidebar and the drawer. `onNavigate` is what marks it as the drawer. */
  const renderSidebar = (onNavigate?: () => void) => (
    <div className="flex h-full flex-col">
      <div className="flex h-(--app-header-height) shrink-0 items-center gap-2.5 border-b border-line px-4">
        <Link to={ROUTES.overview} onClick={onNavigate} className="flex min-w-0 items-center gap-2.5">
          <BrandMark />
          <span className="truncate text-sm font-semibold">{fa.app.name}</span>
        </Link>

        {/* Only the drawer gets a close button; the persistent sidebar has nothing to close.
            ms-auto pushes it to the trailing edge — the left in RTL. */}
        {onNavigate && (
          <IconButton label={fa.common.closeMenu} onClick={onNavigate} className="ms-auto">
            <CloseIcon />
          </IconButton>
        )}
      </div>

      <nav aria-label={fa.layout.sidebarLabel} className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
        <NavGroup title={fa.nav.sectionMain} entries={visibleMain} onNavigate={onNavigate} />
        <NavGroup title={fa.nav.sectionAdmin} entries={visibleAdmin} onNavigate={onNavigate} />
      </nav>

      {/* The operating mode is the platform's safety invariant, so it is always on screen — not
          folded into a menu. */}
      <div className="shrink-0 border-t border-line px-4 py-4">
        <p className="micro-label">{fa.layout.operatingMode}</p>
        <p className="mt-2 flex items-center gap-2 text-sm">
          <StatusDot tone={isPaper ? 'accent' : 'warn'} />
          <span className="num font-semibold text-ink">{mode}</span>
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
          {isPaper ? fa.layout.paperModeNote : fa.layout.liveModeNote}
        </p>
      </div>
    </div>
  )

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[16.5rem_1fr]">
      {/* Skip link: with the sidebar first in tab order on every page, a keyboard user would
          otherwise walk the whole menu before reaching the content. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:end-3 focus:z-50 focus:rounded-lg focus:bg-accent-fill focus:px-4 focus:py-2 focus:text-accent-on"
      >
        {fa.layout.skipToContent}
      </a>

      {/* Persistent sidebar, wide screens. First grid column, so `dir="rtl"` places it on the right;
          `border-e` is the edge that faces the content, which is the left in RTL. */}
      <aside className="sticky top-0 hidden h-dvh flex-col border-e border-line bg-surface lg:flex">
        {renderSidebar()}
      </aside>

      {/* Drawer, narrow screens. */}
      {isDrawerOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-scrim lg:hidden"
            onClick={() => setIsDrawerOpen(false)}
            aria-hidden="true"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label={fa.layout.sidebarLabel}
            className="fixed inset-y-0 start-0 z-50 w-[17rem] border-e border-line bg-surface shadow-float lg:hidden"
          >
            {renderSidebar(() => setIsDrawerOpen(false))}
          </div>
        </>
      )}

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex h-(--app-header-height) shrink-0 items-center gap-2 border-b border-line bg-ground/85 px-3 backdrop-blur sm:px-5 lg:px-7">
          <IconButton
            label={fa.common.openMenu}
            aria-expanded={isDrawerOpen}
            onClick={() => setIsDrawerOpen(true)}
            className="-ms-1.5 lg:hidden"
          >
            <MenuIcon />
          </IconButton>

          {currentSection && <p className="truncate text-sm font-semibold">{currentSection.label}</p>}

          {/* ms-auto pushes the controls to the trailing edge — left in RTL. */}
          <div className="ms-auto flex items-center gap-1 sm:gap-2">
            <Badge tone={isPaper ? 'accent' : 'warn'}>
              <StatusDot tone={isPaper ? 'accent' : 'warn'} />
              <span className="num font-semibold">{mode}</span>
            </Badge>
            <ThemeToggle />
            <UserMenu onLogout={handleLogout} isLoggingOut={isLoggingOut} />
          </div>
        </header>

        <main id="main-content" className="mx-auto w-full min-w-0 max-w-[84rem] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-9">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function NavGroup({
  title,
  entries,
  onNavigate,
}: {
  title: string
  entries: NavEntry[]
  onNavigate?: () => void
}) {
  // An empty group renders nothing at all — heading included. A section header over no items reads as
  // a loading failure, and for an operator with no admin rights it would advertise a menu that will
  // never appear.
  if (entries.length === 0) return null

  return (
    <div>
      <p className="micro-label px-3 pb-2">{title}</p>
      <ul className="space-y-0.5">
        {entries.map((entry) => (
          <li key={entry.to}>
            <NavLink
              to={entry.to}
              onClick={onNavigate}
              className={({ isActive }) =>
                [
                  'flex h-10 items-center gap-2.5 rounded-xl px-3 text-sm transition-colors',
                  isActive
                    ? 'bg-accent/10 font-semibold text-accent-ink'
                    : 'text-ink-soft hover:bg-surface-muted hover:text-ink',
                ].join(' ')
              }
            >
              <span className="shrink-0" aria-hidden="true">
                {entry.icon}
              </span>
              <span className="truncate">{entry.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  )
}

function UserMenu({ onLogout, isLoggingOut }: { onLogout: () => void; isLoggingOut: boolean }) {
  const { session } = useAuth()
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isOpen) return

    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setIsOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [isOpen])

  if (!session) return null

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label={fa.layout.userMenu}
        className="flex h-9 items-center gap-2 rounded-xl ps-1 pe-2 text-sm transition-colors hover:bg-surface-muted"
      >
        <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-accent/12 text-xs font-bold text-accent-ink">
          {session.fullName.trim().charAt(0) || session.userName.charAt(0)}
        </span>
        {/* dir="auto" so the ellipsis lands at the end of the name rather than the end of the *box*.
            A Latin name in an RTL container is truncated from its own start: "System Administrator"
            renders as "…tem Administrator". Persian names are already right — which is why this is
            auto and not a fixed ltr. */}
        <span dir="auto" className="hidden max-w-32 truncate sm:block">
          {session.fullName || session.userName}
        </span>
        <Chevron isOpen={isOpen} />
      </button>

      {isOpen && (
        // end-0 anchors the panel to the button's trailing edge, so it opens inward rather than off
        // the viewport — on the left in RTL.
        <div
          role="menu"
          className="absolute end-0 mt-2 w-60 overflow-hidden rounded-xl border border-line bg-surface shadow-float"
        >
          <div className="border-b border-line p-3">
            <p dir="auto" className="truncate text-sm font-semibold">
              {session.fullName || session.userName}
            </p>
            <p className="num mt-0.5 truncate text-xs text-ink-muted">{session.userName}</p>
            {session.isSuperAdmin && (
              <Badge tone="warn" className="mt-2.5">
                {fa.layout.superAdmin}
              </Badge>
            )}
            {!session.isSuperAdmin && session.userType && (
              <Badge tone="neutral" className="mt-2.5">
                {session.userType}
              </Badge>
            )}
          </div>

          <div className="p-2">
            <NavLink
              to={ROUTES.changePassword}
              role="menuitem"
              className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-ink-soft transition-colors hover:bg-surface-muted hover:text-ink"
            >
              <KeyIcon />
              {fa.auth.changePasswordTitle}
            </NavLink>

            <button
              type="button"
              role="menuitem"
              onClick={onLogout}
              disabled={isLoggingOut}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-danger-ink transition-colors hover:bg-danger/10 disabled:opacity-60"
            >
              <LogoutIcon />
              {isLoggingOut ? fa.auth.loggingOut : fa.auth.logout}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * The one genuinely directional glyph here, and so the one place an `rtl:` variant is right: a
 * chevron points at the thing it opens, and that side swaps with the writing direction. Logical
 * properties cannot express this — there is no logical `rotate`.
 */
function Chevron({ isOpen }: { isOpen: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      aria-hidden="true"
      className={`size-4 shrink-0 text-ink-faint transition-transform ${isOpen ? 'rotate-180' : ''}`}
    >
      <path d="M5.5 8l4.5 4.5L14.5 8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

const iconClass = 'size-[1.15rem]'

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" className="size-5" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" className="size-4.5" aria-hidden="true">
      <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" strokeLinecap="round" />
    </svg>
  )
}

function GridIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className={iconClass} aria-hidden="true">
      <rect x="3.5" y="3.5" width="7" height="7" rx="2" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="2" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="2" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="2" />
    </svg>
  )
}

function UsersIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className={iconClass} aria-hidden="true">
      <circle cx="9" cy="8" r="3.4" />
      <path d="M2.8 20c.5-3.4 3.1-5.4 6.2-5.4s5.7 2 6.2 5.4" strokeLinecap="round" />
      <path d="M16.2 5.2a3.4 3.4 0 0 1 0 6.4M18 14.9c2 .7 3.3 2.5 3.6 5.1" strokeLinecap="round" />
    </svg>
  )
}

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className={iconClass} aria-hidden="true">
      <path d="M12 3l7.5 3v6c0 4.3-3 7.6-7.5 9-4.5-1.4-7.5-4.7-7.5-9V6L12 3Z" strokeLinejoin="round" />
      <path d="M8.8 12.2l2.4 2.3 4-4.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function KeyIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className={iconClass} aria-hidden="true">
      <circle cx="8" cy="12" r="3.6" />
      <path d="M11.6 12H21M17.6 12v3.2M14.6 12v2.4" strokeLinecap="round" />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className={iconClass} aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.4V12l3.2 2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function ChipIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className={iconClass} aria-hidden="true">
      <rect x="6.5" y="6.5" width="11" height="11" rx="2.5" />
      <path d="M10 3.5v3M14 3.5v3M10 17.5v3M14 17.5v3M3.5 10h3M3.5 14h3M17.5 10h3M17.5 14h3" strokeLinecap="round" />
    </svg>
  )
}

function PulseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className={iconClass} aria-hidden="true">
      <path d="M3 12.5h3.5l2-5.5 3 11 2.5-7 1.8 4h5.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function BotIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className={iconClass} aria-hidden="true">
      <rect x="4" y="8" width="16" height="11" rx="3" />
      <path d="M12 4.5V8" strokeLinecap="round" />
      <circle cx="9" cy="13" r="1.15" fill="currentColor" stroke="none" />
      <circle cx="15" cy="13" r="1.15" fill="currentColor" stroke="none" />
      <path d="M9.5 16.2h5" strokeLinecap="round" />
    </svg>
  )
}

function StopIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className={iconClass} aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" />
      <rect x="9" y="9" width="6" height="6" rx="1.2" />
    </svg>
  )
}

function LogoutIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className={iconClass} aria-hidden="true">
      <path d="M14.5 4.5h3a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-3" strokeLinecap="round" />
      {/* The arrow tracks the writing direction: "out" is leftward in LTR and rightward in RTL. */}
      <g className="rtl:-scale-x-100 origin-center">
        <path d="M10 8l-4 4 4 4M6 12h8" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  )
}
