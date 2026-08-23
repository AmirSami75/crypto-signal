import { fa } from '../i18n/fa'
import { usePlatform, useReadiness } from '../lib/usePlatform'
import { Alert } from '../components/ui/Alert'
import { Badge, StatusDot } from '../components/ui/Badge'
import { Card, Eyebrow } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { StatCard } from '../components/ui/StatCard'

/**
 * The dashboard's landing page: which services are up, which mode the platform is in, and where the
 * order-execution boundary sits.
 *
 * Every figure on this screen comes from a field the API actually returns — `/api/v1/platform` gives
 * the operating mode and the execution-policy sentence, `/health/ready` gives a timestamp and a
 * per-dependency verdict. There is no equity curve, no P&L, no signal count: those endpoints do not
 * exist yet, and a dashboard that invents a number is worse than one with three real ones.
 *
 * Service statuses are read per-dependency rather than painted from the aggregate: `/health/ready`
 * names `postgresql` and `python-ml` individually, and showing the same aggregate verdict on all three
 * cards would report the database as unhealthy whenever the ML service alone was down.
 */

/** Dependency names exactly as `/health/ready` reports them. `null` = the orchestrator itself. */
const SERVICES = [
  { key: 'api', dependency: null, name: fa.overview.orchestrator, detail: fa.overview.orchestratorDetail },
  { key: 'ml', dependency: 'python-ml', name: fa.overview.mlEngine, detail: fa.overview.mlEngineDetail },
  { key: 'db', dependency: 'postgresql', name: fa.overview.database, detail: fa.overview.databaseDetail },
] as const

type ServiceState = 'healthy' | 'unhealthy' | 'connecting'

export function OverviewPage() {
  const { data: platform, error: platformError } = usePlatform()
  const { data: readiness, error: readinessError, isLoading: isReadinessLoading } = useReadiness()

  /**
   * Resolves one card's state.
   *
   * The orchestrator is a special case: if it answered at all it is up, whatever it says about its
   * dependencies. Reporting the API as unhealthy because PostgreSQL is down would contradict the very
   * response that told us so.
   */
  const stateOf = (dependency: string | null): ServiceState => {
    if (dependency === null) {
      if (readinessError) return 'unhealthy'
      return readiness ? 'healthy' : 'connecting'
    }

    if (isReadinessLoading) return 'connecting'

    const reported = readiness?.dependencies?.find((entry) => entry.name === dependency)?.status
    if (!reported) return readinessError ? 'unhealthy' : 'connecting'
    return reported.toLowerCase() === 'healthy' ? 'healthy' : 'unhealthy'
  }

  const stateLabel: Record<ServiceState, string> = {
    healthy: fa.overview.statusHealthy,
    unhealthy: fa.overview.statusUnhealthy,
    connecting: fa.overview.statusConnecting,
  }

  const stateTone: Record<ServiceState, 'success' | 'danger' | 'neutral'> = {
    healthy: 'success',
    unhealthy: 'danger',
    connecting: 'neutral',
  }

  const states = SERVICES.map((service) => stateOf(service.dependency))
  const healthyCount = states.filter((state) => state === 'healthy').length
  const isSettled = !states.includes('connecting')

  const mode = platform?.operatingMode ?? 'PAPER'
  const isPaper = mode.toUpperCase() === 'PAPER'

  // en-GB rather than fa-IR: the calendar is irrelevant for a clock reading, and a Persian locale
  // would render ۱۴:۳۲:۰۵ — this product shows Latin digits everywhere.
  const checkedAt = (() => {
    if (!readiness?.timestamp) return null
    const parsed = new Date(readiness.timestamp)
    if (Number.isNaN(parsed.getTime())) return null
    return parsed.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  })()

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[1.375rem] font-semibold sm:text-2xl">{fa.overview.title}</h1>
        <p className="mt-1.5 text-sm text-ink-muted">{fa.overview.subtitle}</p>
      </header>

      {/* Only the platform endpoint failing is worth an alert: it is the one that carries the
          operating mode, and not knowing the mode is the thing that actually matters here. */}
      {platformError && <Alert tone="error">{fa.overview.unreachable}</Alert>}

      <section aria-label={fa.overview.summaryLabel} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {/* The mode is also in the header and the sidebar. That repetition is deliberate — it is the
            platform's safety invariant — and this is the only one of the three with room to say what
            the mode *means*. */}
        <StatCard
          label={fa.overview.modeCardLabel}
          value={mode}
          caption={isPaper ? fa.layout.paperModeNote : fa.layout.liveModeNote}
          trailing={<StatusDot tone={isPaper ? 'accent' : 'warn'} />}
        />

        <StatCard
          label={fa.overview.servicesCardLabel}
          value={`${healthyCount}/${SERVICES.length}`}
          caption={fa.overview.servicesCardCaption}
          trailing={
            isSettled ? (
              <StatusDot tone={healthyCount === SERVICES.length ? 'success' : 'danger'} />
            ) : (
              <Spinner size="sm" />
            )
          }
        />

        <StatCard
          label={fa.overview.lastCheckLabel}
          value={checkedAt ?? '—'}
          caption={checkedAt ? undefined : fa.overview.lastCheckPending}
          trailing={checkedAt ? <StatusDot tone="success" /> : undefined}
        />
      </section>

      <section aria-label={fa.overview.servicesLabel} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {SERVICES.map((service, index) => {
          const state = states[index]
          return (
            <Card key={service.key} as="article" className="p-5">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-sm font-semibold">{service.name}</h2>
                <Badge tone={stateTone[state]} className="shrink-0">
                  {state === 'connecting' ? (
                    <Spinner size="sm" decorative />
                  ) : (
                    <StatusDot tone={state === 'healthy' ? 'success' : 'danger'} />
                  )}
                  {stateLabel[state]}
                </Badge>
              </div>

              <p className="mt-2.5 text-sm leading-relaxed text-ink-muted">{service.detail}</p>
            </Card>
          )
        })}
      </section>

      <Card as="section" className="p-6 sm:p-7">
        <Eyebrow>{fa.overview.boundaryLabel}</Eyebrow>

        {/* The server's own sentence when it is reachable — it is the authoritative statement of the
            policy, and hard-coding a translation of it here could drift from the actual behaviour. */}
        <h2 className="mt-2.5 text-base leading-relaxed font-semibold sm:text-lg">
          {platform?.executionPolicy ?? fa.overview.boundaryFallback}
        </h2>

        <div className="mt-6 space-y-2.5">
          <Flow
            steps={[fa.overview.flowDashboard, fa.overview.flowOrchestrator, fa.overview.flowExchange]}
          />
          <Flow
            steps={[fa.overview.flowMarketData, fa.overview.flowMl, fa.overview.flowSignalOnly]}
            muted
          />
        </div>
      </Card>
    </div>
  )
}

/**
 * One pipeline of steps, read in the document's own direction.
 *
 * The arrow is `←` rather than `→`: in RTL the sequence reads right to left, so an arrow drawn
 * pointing right would point back at the step it came from. This is the same class of decision as the
 * chevron in the dashboard layout — a directional glyph has to follow the writing direction, and no
 * logical property expresses it.
 */
function Flow({ steps, muted = false }: { steps: readonly string[]; muted?: boolean }) {
  return (
    <ol className={`flex flex-wrap items-center gap-2 text-xs ${muted ? 'opacity-70' : ''}`}>
      {steps.map((step, index) => (
        <li key={step} className="flex items-center gap-2">
          {index > 0 && (
            <span aria-hidden="true" className="text-ink-faint">
              ←
            </span>
          )}
          <Badge tone={index === 0 ? 'accent' : 'neutral'}>{step}</Badge>
        </li>
      ))}
    </ol>
  )
}
