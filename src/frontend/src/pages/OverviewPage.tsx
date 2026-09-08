import { useCallback, useState } from 'react'
import { Link } from 'react-router'
import { fa } from '../i18n/fa'
import { usePlatform, useReadiness } from '../lib/usePlatform'
import { Alert } from '../components/ui/Alert'
import { Badge, StatusDot } from '../components/ui/Badge'
import { BarChart, CandleChart } from '../components/ui/Charts'
import { Card, Eyebrow } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { Spinner } from '../components/ui/Spinner'
import { StatCard } from '../components/ui/StatCard'
import { BotStatusBadge, OperatingModeBadge, venueLabel } from '../components/trading/TradingBadges'
import { can, PERMISSIONS } from '../auth/permissions'
import { useAuth } from '../auth/AuthContext'
import { api } from '../lib/api'
import type { BotSummary, ChartCandle, OutcomeReport, PagedResult } from '../lib/apiTypes'
import { ROUTES, botDetailPath, botMonitorPath } from '../routes'
import { buttonClasses } from '../components/ui/Button'
import {
  countText,
  dateTimeText,
  moneyText,
  percentText,
  priceText,
  signedMoneyText,
} from '../lib/tradingFormat'
import { useResource } from '../lib/useResource'
import { useInterval } from '../lib/useInterval'

/**
 * The dashboard's landing page: which services are up, which mode the platform is in, where the
 * order-execution boundary sits, and whether the bot fleet is doing anything.
 *
 * Every figure on this screen comes from a field an API actually returns — `/api/v1/platform` gives
 * the operating mode and the execution-policy sentence, `/health/ready` a timestamp plus
 * per-dependency verdicts, and the bot listing its counts and per-bot lifecycle fields. No equity
 * curve, no invented totals: money figures appear only as the server-computed per-bot values the
 * listing already carries, because a dashboard that invents or derives a number is worse than one
 * with real ones.
 *
 * Service statuses are read per-dependency rather than painted from the aggregate: `/health/ready`
 * names `postgresql` and `python-ml` individually, and showing the same aggregate verdict on all three
 * cards would report the database as unhealthy whenever the ML service alone was down.
 *
 * The fleet section renders only for operators holding `Bot.Get`; for everyone else it was never
 * there rather than erroring.
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

  const { session } = useAuth()
  // An operator without Bot.Get simply gets no bot figures rather than a 403-shaped hole: the
  // resolver answers with nothing and the cards show their connecting dash for one beat less.
  const canSeeBots = can(session, PERMISSIONS.botGet)

  /**
   * One listing call, first page, high cap: a fleet small enough to fit on this screen is small
   * enough to read in a single response, and per-bot pages live on their own screens. `null` when
   * the permission is absent, so no request leaves and no error banner fires.
   */
  const botsFetcher = useCallback(
    (signal?: AbortSignal): Promise<PagedResult<BotSummary> | null> =>
      canSeeBots ? api.bots.paged({ pageNumber: 1, pageSize: 200 }, {}, signal) : Promise.resolve(null),
    [canSeeBots],
  )
  const {
    data: botsPage,
    error: botsError,
    isLoading: isBotsLoading,
  } = useResource(botsFetcher)

  /** Integer counts only. Money totals stay server-side — see `tradingFormat.ts`'s standing rule. */
  const bots = botsPage?.items ?? []
  const activeBots = bots.filter((bot) => bot.status === 'Active')
  const totalBots = botsPage?.totalRecords ?? 0
  const openPositions = bots.reduce((sum, bot) => sum + bot.openPositionCount, 0)
  const blockedCount = activeBots.filter((bot) => bot.isBlockedByKillSwitch).length

  // The self-learning loop's read side, for operators holding ModelOutcomes.Get. A null (no
  // permission) renders as an absent card, same discipline as the fleet section above.
  const canSeeOutcomes = can(session, PERMISSIONS.modelOutcomesGet)
  const outcomesFetcher = useCallback(
    (signal?: AbortSignal): Promise<OutcomeReport | null> =>
      canSeeOutcomes ? api.outcomes.all(signal) : Promise.resolve(null),
    [canSeeOutcomes],
  )
  const { data: outcomes } = useResource(outcomesFetcher)

  // Calibration buckets, prepared once per report: bar heights are win shares, gaps stay visible
  // where a bucket has no closed trades yet.
  const bucketLabels = (outcomes?.calibrationBuckets ?? []).map(
    (bucket) => `${Math.round(bucket.lower * 100)}–${Math.round(bucket.upper * 100)}`,
  )
  const bucketValues = (outcomes?.calibrationBuckets ?? []).map((bucket) =>
    bucket.trades > 0 ? bucket.wins / bucket.trades : null,
  )

  // Per-bot realised P&L bars. Each row is one server-computed figure scaled against the largest
  // magnitude in the fleet — nothing is added up here; the only total on this page is the server's.
  const pnlMax = Math.max(1e-9, ...bots.map((bot) => Math.abs(bot.realizedPnl)))

  /** Market pulse anchors to the first active bot's market, else the first bot there is. */
  const pulseBot = activeBots[0] ?? bots[0]


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

      {/* The one state that outranks every other number on this page: a fleet that is running but
          refused. Redundant with the per-bot pill on purpose — this screen is where someone lands
          after "why are we not trading?", before they know to look at a bot's own row. */}
      {blockedCount > 0 && <Alert tone="warn">{fa.overview.killSwitchBlockAlert}</Alert>}

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

      {/* The fleet row. Same honesty rule as the rest of the page: counts the API actually sent,
          dots only where a state is real. While the listing loads, the cards say so with a spinner
          rather than zeros — a zero that lasts 300ms still reads as "everything stopped". */}
      <section aria-label={fa.overview.botsSectionLabel} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard
          label={fa.overview.activeBotsLabel}
          value={`${countText(activeBots.length)}/${countText(totalBots)}`}
          caption={botsError && !isBotsLoading ? fa.overview.botsLoadFailed : fa.overview.activeBotsCaption}
          trailing={
            isBotsLoading ? (
              <Spinner size="sm" />
            ) : (
              <StatusDot tone={activeBots.length > 0 && !botsError ? 'success' : 'neutral'} />
            )
          }
        />

        <StatCard
          label={fa.overview.openPositionsLabel}
          value={isBotsLoading && !botsPage ? '—' : countText(openPositions)}
          caption={fa.overview.openPositionsCaption}
        />

        <StatCard
          label={fa.overview.blockedBotsLabel}
          value={countText(blockedCount)}
          caption={blockedCount > 0 ? fa.overview.blockedBotsSome : fa.overview.blockedBotsZero}
          trailing={<StatusDot tone={blockedCount > 0 ? 'danger' : 'neutral'} />}
        />
      </section>

      {/* Fleet pulse: the market one bot actually watches, beside what every bot has earned. Two
          cards because they answer different questions at different cadences — price moves in
          minutes, realised P&L in closed trades. */}
      <section aria-label={fa.overview.botsSectionLabel} className="grid gap-4 xl:grid-cols-3">
        {pulseBot && (
          <Card as="article" className="p-5">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h2 className="micro-label">{fa.overview.marketPulseLabel}</h2>
              <span className="num text-xs text-ink-faint" dir="ltr">
                {pulseBot.symbol}
              </span>
            </div>
            <p className="mt-1.5 mb-3 text-xs leading-relaxed text-ink-muted">{fa.overview.marketPulseDetail}</p>
            <MarketPulse venue={pulseBot.venue} symbol={pulseBot.symbol} />
          </Card>
        )}

        <Card as="article" className={`p-5 ${pulseBot ? 'xl:col-span-2' : 'xl:col-span-3'}`}>
          <h2 className="micro-label">{fa.overview.pnlByBotLabel}</h2>
          <p className="mt-1.5 mb-4 text-xs leading-relaxed text-ink-muted">{fa.overview.pnlByBotDetail}</p>

          {isBotsLoading && bots.length === 0 ? (
            <div className="space-y-3" aria-busy="true" aria-label={fa.common.loading} role="status">
              <div className="h-4 animate-pulse rounded bg-surface-muted" />
              <div className="h-4 animate-pulse rounded bg-surface-muted" />
              <div className="h-4 animate-pulse rounded bg-surface-muted" />
            </div>
          ) : bots.length === 0 ? (
            <p className="py-6 text-center text-sm text-ink-faint">{fa.overview.pnlEmpty}</p>
          ) : (
            <ul className="space-y-3" role="list" aria-label={fa.overview.pnlByBotLabel}>
              {bots.map((bot) => {
                const share = Math.abs(bot.realizedPnl) / pnlMax
                const tone = bot.realizedPnl > 0 ? 'bg-success' : bot.realizedPnl < 0 ? 'bg-danger' : 'bg-line'
                return (
                  <li key={bot.id} className="grid grid-cols-[minmax(6rem,10rem)_1fr_auto] items-center gap-3">
                    <Link
                      to={botDetailPath(bot.id)}
                      className="truncate text-sm font-medium text-ink hover:text-accent"
                    >
                      {bot.name}
                    </Link>

                    <div
                      className="h-2.5 overflow-hidden rounded-full bg-surface-muted"
                      role="progressbar"
                      aria-valuenow={Math.round(share * 100)}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`${bot.name}: ${signedMoneyText(bot.realizedPnl)}`}
                    >
                      <div
                        className={`h-full rounded-full transition-[width] ${tone}`}
                        style={{ width: `${Math.max(share * 100, bot.realizedPnl === 0 ? 0 : 2)}%` }}
                      />
                    </div>

                    <span
                      className={`num w-24 text-end text-xs font-medium ${
                        bot.realizedPnl > 0 ? 'text-success' : bot.realizedPnl < 0 ? 'text-danger' : 'text-ink-faint'
                      }`}
                    >
                      {signedMoneyText(bot.realizedPnl)}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
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

      {/* Model health. Flat or inverted calibration buckets are the earliest visible drift signal,
          which makes this chart the cheapest early warning on the page. Hidden entirely for
          operators without ModelOutcomes.Get, and while the sample is empty — a 0/0 win rate is
          not evidence of anything. */}
      {canSeeOutcomes && outcomes && outcomes.sampleSize > 0 && (
        <Card as="section" className="p-6 sm:p-7">
          <Eyebrow>{fa.overview.mlHealthLabel}</Eyebrow>

          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label={fa.overview.mlSampleLabel} value={countText(outcomes.sampleSize)} className="border-line/60 p-4" />
            <StatCard label={fa.overview.mlWinsLabel} value={countText(outcomes.wins)} className="border-line/60 p-4" />
            <StatCard label={fa.overview.mlLossesLabel} value={countText(outcomes.losses)} className="border-line/60 p-4" />
            <StatCard
              label={fa.overview.mlAvgPnlLabel}
              value={
                <span className={outcomes.averageRealizedPnl >= 0 ? 'text-success' : 'text-danger'}>
                  {signedMoneyText(outcomes.averageRealizedPnl)}
                </span>
              }
              className="border-line/60 p-4"
            />
          </div>

          <div className="mt-7 grid gap-8 lg:grid-cols-2">
            <div>
              <h3 className="text-sm font-semibold">{fa.overview.calibrationLabel}</h3>
              <p className="mb-4 mt-1 text-xs leading-relaxed text-ink-muted">{fa.overview.calibrationDetail}</p>
              <BarChart values={bucketValues} labels={bucketLabels} ariaLabel={fa.overview.calibrationLabel} />
            </div>

            <div>
              <h3 className="text-sm font-semibold">{fa.overview.perSymbolLabel}</h3>
              <ul className="mt-3 divide-y divide-line">
                {outcomes.perSymbol.map((row) => {
                  const winShare = row.trades > 0 ? row.wins / row.trades : null
                  return (
                    <li key={row.symbol} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                      <span className="num font-medium text-ink" dir="ltr">{row.symbol}</span>

                      <span className="num text-xs text-ink-muted">
                        {`${countText(row.trades)} ${fa.overview.tradesUnit}${winShare !== null ? ` · ${percentText(winShare * 100, 0)}` : ''}`}
                      </span>

                      <span
                        className={`num font-medium ${
                          row.totalPnl > 0 ? 'text-success' : row.totalPnl < 0 ? 'text-danger' : 'text-ink-faint'
                        }`}
                      >
                        {signedMoneyText(row.totalPnl)}
                      </span>
                    </li>
                  )
                })}
              </ul>
            </div>
          </div>
        </Card>
      )}

      {/* The running fleet, one row each. Whole rows are links to the monitor screen — the detail
          pages own per-tick forensics; this page answers "is anything alive, and is it the mode I
          think it is". Venue text and mode pill sit beside every name because the operating mode is
          the platform's safety invariant and repetition of *that* kind is cheap. */}
      {canSeeBots && (
        <Card as="section" className="p-6 sm:p-7">
          <Eyebrow>{fa.overview.botsSectionLabel}</Eyebrow>
          <p className="mt-2.5 text-sm leading-relaxed text-ink-muted">{fa.overview.botsSectionDetail}</p>

          {botsError && !botsPage ? (
            <Alert tone="error" className="mt-5">{fa.overview.botsLoadFailed}</Alert>
          ) : activeBots.length === 0 ? (
            <EmptyState
              className="mt-6"
              title={isBotsLoading ? fa.overview.statusConnecting : fa.overview.botsEmptyTitle}
              body={isBotsLoading ? undefined : fa.overview.botsEmptyBody}
              action={
                !isBotsLoading && (
                  <Link to={ROUTES.bots} className={buttonClasses({ variant: 'secondary', size: 'sm' })}>
                    {fa.nav.bots}
                  </Link>
                )
              }
            />
          ) : (
            <ul className="mt-5 divide-y divide-line">
              {activeBots.map((bot) => (
                <li key={bot.id}>
                  <Link
                    to={botMonitorPath(bot.id)}
                    className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3.5 transition-colors hover:bg-surface-muted/60"
                  >
                    <span className="font-semibold text-ink">{bot.name}</span>

                    <span className="num text-xs text-ink-muted">
                      {bot.symbol} · {bot.interval}
                    </span>

                    <Badge tone="neutral">{venueLabel(bot.venue)}</Badge>
                    <OperatingModeBadge mode={bot.operatingMode} />

                    {bot.leverage > 1 && (
                      <Badge tone="warn">
                        <span className="num">{`${fa.overview.leverageUnit}${countText(bot.leverage)}`}</span>
                      </Badge>
                    )}

                    {bot.isBlockedByKillSwitch && (
                      <Badge tone="danger">{fa.killSwitches.stateEngaged}</Badge>
                    )}

                    {/* Trailing block: what it holds, what it earned, when it last thought. The P&L
                        sign classes mirror the intent table's — green means money in. */}
                    <span className="ms-auto flex items-center gap-x-4 text-xs text-ink-muted">
                      <span className="num">
                        {bot.openPositionCount > 0
                          ? `${countText(bot.openPositionCount)} ${fa.overview.openPositionsLabel}`
                          : '—'}
                      </span>

                      <span
                        className={`num font-medium ${
                          bot.realizedPnl > 0 ? 'text-success-ink' : bot.realizedPnl < 0 ? 'text-danger-ink' : ''
                        }`}
                      >
                        {signedMoneyText(bot.realizedPnl)}
                      </span>

                      <span className="num">{dateTimeText(bot.lastTickAt)}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

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

/**
 * Live candle panel for the market the fleet is currently pointed at.
 *
 * Same polling discipline as the monitor page's `LivePriceCard` — venue candles through our API,
 * own interval, refresh on a timer — but summary-shaped: one large last price with its window
 * direction, and a compact chart. The overview glances; the monitor interrogates.
 */
function MarketPulse({ venue, symbol }: { venue: string; symbol: string }) {
  const [candles, setCandles] = useState<ChartCandle[] | null>(null)
  const [failed, setFailed] = useState(false)

  const refetch = useCallback(() => {
    api.charts
      .candles(venue, symbol, '15m', 96)
      .then((data) => {
        setCandles(data)
        setFailed(false)
      })
      // A pulse that cannot be read shows as quiet absence, not as an alarm — the status cards
      // above already own "is anything wrong".
      .catch(() => setFailed(true))
  }, [venue, symbol])

  useInterval(refetch, 60_000)

  if (failed && !candles) return null

  if (!candles)
    return (
      <div className="flex h-[150px] items-center justify-center">
        <Spinner />
      </div>
    )

  const last = candles[candles.length - 1]
  const first = candles[0]
  const rising = last.close >= first.open

  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-3">
        <span className={`num text-xl font-semibold ${rising ? 'text-success' : 'text-danger'}`} dir="ltr">
          {priceText(last.close)}
        </span>
        <span className={`num text-xs ${rising ? 'text-success' : 'text-danger'}`} dir="ltr">
          {rising ? '▲' : '▼'} {moneyText(Math.abs(last.close - first.open))}
        </span>
        <span className="num ms-auto text-xs text-ink-faint" dir="ltr">
          15m
        </span>
      </div>

      <CandleChart candles={candles} ariaLabel={`${symbol} 15m`} height={110} />

      <p className="num text-[0.6875rem] text-ink-faint" dir="ltr">
        {dateTimeText(candles[0]?.openTime)} → {dateTimeText(last?.openTime)}
      </p>
    </div>
  )
}
