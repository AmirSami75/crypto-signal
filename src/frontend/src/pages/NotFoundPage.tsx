import { Link } from 'react-router'
import { fa } from '../i18n/fa'
import { buttonClasses } from '../components/ui/Button'
import { BrandMark } from '../components/BrandMark'
import { ROUTES } from '../routes'

/**
 * 404, rendered outside both shells.
 *
 * Deliberately unauthenticated: a mistyped URL should say so whether or not anyone is signed in, and
 * putting this behind the dashboard guard would answer "not found" with a redirect to the login page —
 * which tells the user the wrong thing about what went wrong. The link back points at the dashboard,
 * where the guard will do its normal job.
 *
 * The numeral is grey rather than accent-coloured. A 404 is not a feature to draw the eye to, and the
 * accent is scarce on purpose in a design with no shadows to fall back on.
 */
export function NotFoundPage() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-7 p-6 text-center">
      <BrandMark className="size-10" />

      <div>
        <p className="num text-6xl font-semibold text-ink-faint">404</p>
        <h1 className="mt-5 text-lg font-semibold">{fa.notFound.title}</h1>
        <p className="mt-2 max-w-sm text-sm leading-relaxed text-ink-muted">{fa.notFound.body}</p>
      </div>

      <Link to={ROUTES.overview} className={buttonClasses({ variant: 'outline' })}>
        {fa.notFound.back}
      </Link>
    </main>
  )
}
