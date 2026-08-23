import { Link, Outlet } from 'react-router'
import { fa } from '../i18n/fa'
import { usePlatform } from '../lib/usePlatform'
import { Badge, StatusDot } from '../components/ui/Badge'
import { ThemeToggle } from '../components/ThemeToggle'
import { ROUTES } from '../routes'
import { BrandMark } from '../components/BrandMark'

/**
 * Shell for the pages that sit outside the dashboard: login, registration, forced password change.
 *
 * One centred column, on the page ground, with no card around it. The two-column marketing panel this
 * replaced was the opposite of minimal — a screen of pitch beside a four-field form — and on a white
 * ground a bordered card would only add a box inside a box. What is left is the brand, the form, and
 * the one fact someone signing in has to know before they sign in.
 *
 * That fact is the operating-mode badge, and it is on the *unauthenticated* screens on purpose.
 * `PAPER` is the platform's safety invariant; discovering it after the fact is how a paper trade gets
 * mistaken for a real one.
 *
 * The header mirrors the dashboard's: same `--app-header-height`, brand on the leading edge, theme
 * toggle on the trailing one — so signing in does not feel like arriving at a different product.
 */
export function AuthLayout() {
  const { data: platform } = usePlatform()
  const mode = platform?.operatingMode ?? 'PAPER'
  const isPaper = mode.toUpperCase() === 'PAPER'

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-(--app-header-height) shrink-0 items-center px-4 sm:px-7">
        <Link to={ROUTES.login} className="flex items-center gap-2.5">
          <BrandMark />
          <span className="text-sm font-semibold">{fa.app.name}</span>
        </Link>

        {/* ms-auto sends the toggle to the trailing edge — the left in RTL. */}
        <div className="ms-auto">
          <ThemeToggle />
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-5 py-8 sm:py-12">
        <div className="w-full max-w-[26rem]">
          <Outlet />
        </div>
      </main>

      <footer className="shrink-0 px-5 pb-8">
        <div className="mx-auto flex max-w-[26rem] flex-wrap items-center justify-center gap-x-2.5 gap-y-2">
          <Badge tone={isPaper ? 'accent' : 'warn'}>
            <StatusDot tone={isPaper ? 'accent' : 'warn'} />
            {fa.layout.operatingMode}: <span className="num font-semibold">{mode}</span>
          </Badge>
          <span className="text-xs text-ink-muted">
            {isPaper ? fa.layout.paperModeNote : fa.layout.liveModeNote}
          </span>
        </div>
      </footer>
    </div>
  )
}
