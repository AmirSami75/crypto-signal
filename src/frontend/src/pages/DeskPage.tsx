import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { PERMISSIONS, can } from '../auth/permissions'
import { Alert } from '../components/ui/Alert'
import { Badge, StatusDot } from '../components/ui/Badge'
import { buttonClasses } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import { EmptyState } from '../components/ui/EmptyState'
import { SectionHeader } from '../components/ui/SectionHeader'
import { Skeleton } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'
import {
  BotStatusBadge,
  DirectionBadge,
  auditEventLabel,
} from '../components/trading/TradingBadges'
import { fa } from '../i18n/fa'
import { api } from '../lib/api'
import type {
  BotAuditEvent,
  BotAuditEventTypeName,
  BotSummary,
  MlModelInfo,
  PagedResult,
  ScannerSignal,
} from '../lib/apiTypes'
import {
  countText,
  dateTimeText,
  digestText,
  priceText,
  shareText,
  timeText,
} from '../lib/tradingFormat'
import { useInterval } from '../lib/useInterval'
import { useResource } from '../lib/useResource'
import { ROUTES, botMonitorPath } from '../routes'

/**
 * The operator's live desk.
 *
 * Four independent reads, one screen: the fleet listing, the newest scanner proposals, the served
 * model's identity, and three audit events per visible bot. Each is its own `useResource` so a
 * failure in one annotates the page instead of blanking it — the whole point of a desk is that the
 * rest of the tape keeps printing while one feed is down.
 *
 * The page re-reads every 15s through `useInterval`, and the clock ticks every second so the
 * relative ages and the freshness pill stay truthful between polls. Fetchers are memoised with
 * serialised dependency keys (the same discipline as ScannerPage and BotsPage): an inline arrow or
 * an object literal in the dependency list would give `useResource` a new fetcher identity on every
 * render and refetch forever.
 *
 * Audit is the one read that fans out. It is a per-bot endpoint and hooks cannot be called in a
 * loop, so one resource fetches the three newest events for each visible bot in parallel. A single
 * bot's refusal is recorded as a failed slice rather than rejecting the whole feed; only a total
 * failure surfaces as an error.
 */

const REFRESH_MS = 15_000
/** The header pill calls the data live while the last successful read is younger than this. */
const LIVE_WINDOW_MS = 30_000
const FLEET_SIZE = 6
const FEED_CAP = 12
const AUDIT_PER_BOT = 3
const SCANNER_PAGE_SIZE = 50
const OPPORTUNITY_LIMIT = 12

const EMPTY_BOTS: BotSummary[] = []
const EMPTY_SIGNALS: ScannerSignal[] = []
const EMPTY_EVENTS: BotAuditEvent[] = []
const EMPTY_AUDITS: BotAuditSlice[] = []

/** The shape the scanner resource takes when the operator may not read the scanner at all. */
const EMPTY_SCANNER_PAGE: PagedResult<ScannerSignal> = {
  totalRecords: 0,
  items: [],
  pageNumber: 1,
  pageSize: 0,
  count: 0,
}

type BotAuditSlice = {
  botId: string
  events: BotAuditEvent[]
  /** One bot's audit endpoint refused or failed; the other slices are still good. */
  failed: boolean
}

type FeedEntry = {
  event: BotAuditEvent
  botName: string
}

export function DeskPage() {
  const { session } = useAuth()

  // The route is gated on Bot.Get, so the supplementary feeds are permission-gated here rather
  // than left to fire a 200-with-`isSuccess:false` refusal every 15 seconds. A missing privilege
  // reads as an absent panel with its reason, not as a page-wide error.
  const canReadScanner = can(session, PERMISSIONS.scannerGet)
  const canReadModel = can(session, PERMISSIONS.mlGetModel)
  const canReadAudit = can(session, PERMISSIONS.botHistoryGetAudit)

  const [now, setNow] = useState(() => Date.now())
  const [lastRefreshAt, setLastRefreshAt] = useState<number | null>(null)

  const botsFetcher = useCallback(
    (signal: AbortSignal) => api.bots.paged({ pageNumber: 1, pageSize: 200 }, {}, signal),
    [],
  )
  const botsResource = useResource(botsFetcher)

  const scannerFetcher = useCallback(
    (signal: AbortSignal): Promise<PagedResult<ScannerSignal>> =>
      canReadScanner
        ? api.scanner.paged({ pageNumber: 1, pageSize: SCANNER_PAGE_SIZE }, {}, signal)
        : Promise.resolve(EMPTY_SCANNER_PAGE),
    [canReadScanner],
  )
  const scannerResource = useResource(scannerFetcher)

  const modelFetcher = useCallback(
    (signal: AbortSignal): Promise<MlModelInfo | null> =>
      canReadModel ? api.model.get(signal) : Promise.resolve(null),
    [canReadModel],
  )
  const modelResource = useResource(modelFetcher)

  const bots = botsResource.data?.items ?? EMPTY_BOTS
  const scannerSignals = scannerResource.data?.items ?? EMPTY_SIGNALS
  const model = modelResource.data

  /**
   * Fleet order: the running bots first, then the listing's own order. The desk is where an
   * operator looks for what is live, so a fleet larger than six must not spend its visible slots on
   * stopped drafts while an Active bot sits on page two of the same response.
   */
  const fleet = useMemo(() => {
    const activeFirst = [...bots].sort(
      (a, b) => Number(b.status === 'Active') - Number(a.status === 'Active'),
    )
    return activeFirst.slice(0, FLEET_SIZE)
  }, [bots])

  // Serialised, not an array: an array literal in the dependency list is a new identity each
  // render and would restart the audit read on every one-second tick.
  const fleetIdsKey = useMemo(() => fleet.map((bot) => bot.id).join(','), [fleet])

  const auditFetcher = useCallback(
    async (signal: AbortSignal): Promise<BotAuditSlice[]> => {
      if (!canReadAudit || fleetIdsKey.length === 0) return []

      const ids = fleetIdsKey.split(',')
      const settled = await Promise.allSettled(
        ids.map((id) => api.botHistory.audit(id, { pageNumber: 1, pageSize: AUDIT_PER_BOT }, signal)),
      )

      // An abort is the read being replaced, not a per-bot failure to report.
      if (signal.aborted) throw new DOMException('The read was aborted.', 'AbortError')

      let firstFailure: unknown = null
      const slices = settled.map((outcome, index): BotAuditSlice => {
        if (outcome.status === 'fulfilled') {
          return { botId: ids[index], events: outcome.value.items ?? [], failed: false }
        }
        firstFailure ??= outcome.reason
        return { botId: ids[index], events: [], failed: true }
      })

      if (slices.every((slice) => slice.failed)) throw firstFailure
      return slices
    },
    [canReadAudit, fleetIdsKey],
  )
  const auditResource = useResource(auditFetcher)

  const audits = auditResource.data ?? EMPTY_AUDITS

  // Any successful read is a refresh. A failed refetch keeps its previous data by design, so the
  // stamp ages out and the pill turns stale instead of lying about a fresh poll.
  useEffect(() => {
    if (!botsResource.data && !scannerResource.data && !modelResource.data && audits.length === 0) return
    setLastRefreshAt(Date.now())
  }, [botsResource.data, scannerResource.data, modelResource.data, audits])

  useInterval(() => setNow(Date.now()), 1_000)

  const refetchBots = botsResource.refetch
  const refetchScanner = scannerResource.refetch
  const refetchModel = modelResource.refetch
  const refetchAudit = auditResource.refetch
  useInterval(() => {
    refetchBots()
    refetchScanner()
    refetchModel()
    refetchAudit()
  }, REFRESH_MS)

  const activeBots = bots.filter((bot) => bot.status === 'Active').length
  const totalBots = botsResource.data?.totalRecords ?? 0
  const openPositions = bots.reduce((sum, bot) => sum + bot.openPositionCount, 0)
  const blockedBots = bots.filter((bot) => bot.isBlockedByKillSwitch).length

  // The scanner orders by |24h change| × log10(volume), which is a volume signal, not an edge
  // signal — so the desk ranks the page it received by Score before cutting to its twelve rows.
  const opportunities = useMemo(
    () => [...scannerSignals].sort((a, b) => b.score - a.score).slice(0, OPPORTUNITY_LIMIT),
    [scannerSignals],
  )
  const maxAbsScore = opportunities.reduce((max, signal) => Math.max(max, Math.abs(signal.score)), 0)
  const bestScore = opportunities.length > 0 ? opportunities[0].score : null

  const leadBot = fleet.find((bot) => bot.status === 'Active') ?? null
  const leadEvents = leadBot
    ? audits.find((slice) => slice.botId === leadBot.id)?.events ?? EMPTY_EVENTS
    : EMPTY_EVENTS

  /** Union of the per-bot audit slices, newest first, capped at one screenful. */
  const feed = useMemo<FeedEntry[]>(() => {
    const names = new Map(fleet.map((bot) => [bot.id, bot.name]))
    return audits
      .flatMap((slice) =>
        slice.events.map((event) => ({
          event,
          botName: names.get(slice.botId) ?? fa.desk.unknownBot,
        })),
      )
      .sort(
        (a, b) =>
          auditStamp(b.event) - auditStamp(a.event) || b.event.sequence - a.event.sequence,
      )
      .slice(0, FEED_CAP)
  }, [audits, fleet])

  const sourceErrors: { label: string; message: string }[] = []
  if (botsResource.error) sourceErrors.push({ label: fa.desk.botsLoadFailed, message: botsResource.error })
  if (scannerResource.error) sourceErrors.push({ label: fa.desk.scannerLoadFailed, message: scannerResource.error })
  if (modelResource.error) sourceErrors.push({ label: fa.desk.modelLoadFailed, message: modelResource.error })
  if (auditResource.error) sourceErrors.push({ label: fa.desk.feedLoadFailed, message: auditResource.error })

  // A few bots' audit endpoints can refuse while others answer; that partial loss is invisible in
  // `auditResource.error`, so it gets its own line rather than silently shortening the feed.
  const failedAuditSlices = audits.filter((slice) => slice.failed).length
  if (failedAuditSlices > 0 && !auditResource.error) {
    sourceErrors.push({
      label: fa.desk.feedPartialFailed,
      message: `${countText(failedAuditSlices)} ${fa.desk.unknownBot}`,
    })
  }

  const botsPending = botsResource.isLoading && !botsResource.data
  const scannerPending = scannerResource.isLoading && !scannerResource.data

  const secondsSinceRefresh =
    lastRefreshAt === null ? null : Math.max(0, Math.floor((now - lastRefreshAt) / 1000))
  const isLive = secondsSinceRefresh !== null && secondsSinceRefresh * 1_000 <= LIVE_WINDOW_MS
  const liveTone: 'success' | 'warn' | 'neutral' =
    lastRefreshAt === null ? 'neutral' : isLive ? 'success' : 'warn'
  const liveLabel =
    lastRefreshAt === null
      ? fa.desk.statusConnecting
      : isLive
        ? fa.desk.statusLive
        : fa.desk.statusStale

  const refreshedClock = lastRefreshAt
    ? new Date(lastRefreshAt).toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : '—'

  const columns: Column<ScannerSignal>[] = [
    {
      key: 'symbol',
      header: fa.scanner.symbol,
      cell: (signal) => (
        <span className="num text-sm font-medium" dir="ltr">
          {signal.symbol}
        </span>
      ),
    },
    {
      key: 'direction',
      header: fa.scanner.direction,
      cell: (signal) => <DirectionBadge direction={signal.direction} />,
    },
    {
      key: 'score',
      header: fa.desk.colScore,
      className: 'whitespace-nowrap',
      cell: (signal) => <ScoreMeter score={signal.score} max={maxAbsScore} />,
    },
    {
      key: 'confidence',
      header: fa.scanner.confidence,
      className: 'whitespace-nowrap',
      cell: (signal) => (
        <span className="num text-sm">{shareText(signal.confidence, 1)}</span>
      ),
    },
    {
      key: 'strategy',
      header: fa.scanner.strategy,
      className: 'whitespace-nowrap',
      cell: (signal) => (
        <Badge tone="neutral">
          <span className="latin">{signal.strategyKey}</span>
        </Badge>
      ),
    },
    {
      key: 'atr',
      header: fa.scanner.atr,
      className: 'whitespace-nowrap',
      cell: (signal) => <span className="num text-sm">{priceText(signal.atrAtSignal)}</span>,
    },
    {
      key: 'age',
      header: fa.scanner.age,
      className: 'whitespace-nowrap',
      cell: (signal) => (
        <span className="text-xs text-ink-faint" title={dateTimeText(signal.createdAt)}>
          {relativeAge(signal.createdAt, now)}
        </span>
      ),
    },
  ]

  return (
    <div className="space-y-5">
      <header className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-[1.375rem] font-semibold sm:text-2xl">{fa.desk.title}</h1>
            <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-muted">
              {fa.desk.subtitle}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <Badge tone={liveTone}>
              <StatusDot tone={liveTone} pulse={isLive} />
              <span>{liveLabel}</span>
              {secondsSinceRefresh !== null && (
                <span className="num text-[0.6875rem] opacity-80">
                  {`· ${countText(secondsSinceRefresh)} ${fa.desk.secondsAgo}`}
                </span>
              )}
            </Badge>

            <span className="text-xs text-ink-muted">
              {fa.desk.lastRefresh}:{' '}
              <span className="num font-medium text-ink-soft">{refreshedClock}</span>
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl border border-line bg-surface px-3 py-2 text-xs text-ink-muted">
          <span className="inline-flex min-w-0 items-center gap-2">
            <span className="micro-label shrink-0">{fa.desk.modelLabel}</span>
            <span
              className="latin min-w-0 max-w-[15rem] truncate font-medium text-ink-soft sm:max-w-[24rem]"
              title={model ? `${model.modelId} · ${model.modelVersion}` : undefined}
            >
              {model
                ? `${digestText(model.modelId, 8)} · ${model.modelVersion}`
                : canReadModel
                  ? '—'
                  : fa.desk.modelNoAccess}
            </span>
          </span>

          <span className="text-ink-faint">{fa.desk.refreshEvery}</span>
        </div>
      </header>

      {/* One banner for every degraded source. The sections below keep rendering their last good
          data, so this annotates the page rather than replacing it. */}
      {sourceErrors.length > 0 && (
        <Alert tone="error" title={fa.desk.partialFailureTitle}>
          <ul className="space-y-1">
            {sourceErrors.map((source) => (
              <li key={source.label}>
                <span className="font-medium">{source.label}:</span>{' '}
                <span className="break-words">{source.message}</span>
              </li>
            ))}
          </ul>
        </Alert>
      )}

      <section aria-label={fa.desk.kpiLabel} className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-5">
        <StatCard
          label={fa.desk.kpiActiveBots}
          value={
            botsPending ? (
              <Skeleton className="h-7 w-14" />
            ) : (
              `${countText(activeBots)}/${countText(totalBots)}`
            )
          }
          caption={fa.desk.kpiActiveBotsCaption}
          trailing={<StatusDot tone={activeBots > 0 ? 'success' : 'neutral'} />}
          tone={activeBots > 0 ? 'success' : 'neutral'}
        />

        <StatCard
          label={fa.desk.kpiOpenPositions}
          value={botsPending ? <Skeleton className="h-7 w-10" /> : countText(openPositions)}
          caption={fa.desk.kpiOpenPositionsCaption}
          tone={openPositions > 0 ? 'accent' : 'neutral'}
        />

        <StatCard
          label={fa.desk.kpiProposals}
          value={
            scannerPending ? <Skeleton className="h-7 w-10" /> : countText(scannerSignals.length)
          }
          caption={fa.desk.kpiProposalsCaption}
          tone={scannerSignals.length > 0 ? 'accent' : 'neutral'}
        />

        <StatCard
          label={fa.desk.kpiBestScore}
          value={
            scannerPending ? (
              <Skeleton className="h-7 w-20" />
            ) : bestScore === null ? (
              '—'
            ) : (
              signedScore(bestScore)
            )
          }
          caption={fa.desk.kpiBestScoreCaption}
          tone={bestScore !== null && bestScore > 0 ? 'success' : 'neutral'}
        />

        <StatCard
          label={fa.desk.kpiBlockedBots}
          value={botsPending ? <Skeleton className="h-7 w-10" /> : countText(blockedBots)}
          caption={blockedBots > 0 ? fa.desk.kpiBlockedBotsCaption : fa.desk.kpiBlockedBotsNone}
          trailing={<StatusDot tone={blockedBots > 0 ? 'danger' : 'neutral'} />}
          tone={blockedBots > 0 ? 'danger' : 'neutral'}
          className="col-span-2 xl:col-span-1"
        />
      </section>

      <Card as="section" className="p-4 sm:p-6">
        <SectionHeader
          title={fa.desk.opportunitiesTitle}
          subtitle={fa.desk.opportunitiesSubtitle}
          actions={
            <Link
              to={ROUTES.scanner}
              className={buttonClasses({ variant: 'outline', size: 'sm' })}
            >
              {fa.nav.scanner}
            </Link>
          }
        />

        <div className="mt-4">
          <DataTable
            columns={columns}
            rows={opportunities}
            rowKey={(signal) => signal.id}
            isLoading={scannerResource.isLoading}
            isRefreshing={scannerResource.isRefreshing}
            error={scannerResource.error}
            skeletonRows={8}
            emptyTitle={
              canReadScanner ? fa.desk.opportunitiesEmptyTitle : fa.desk.scannerNoAccessTitle
            }
            emptyBody={
              canReadScanner ? fa.desk.opportunitiesEmptyBody : fa.desk.scannerNoAccessBody
            }
          />
        </div>
      </Card>

      <Card as="section" className="p-4 sm:p-6">
        <SectionHeader
          title={fa.desk.fleetTitle}
          subtitle={fa.desk.fleetSubtitle}
          actions={
            <Link to={ROUTES.bots} className={buttonClasses({ variant: 'outline', size: 'sm' })}>
              {fa.desk.fleetLink}
            </Link>
          }
        />

        {botsPending ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true">
            {Array.from({ length: FLEET_SIZE }, (_, index) => (
              <Skeleton key={index} className="h-32" />
            ))}
          </div>
        ) : botsResource.error && !botsResource.data ? (
          <Alert tone="error" className="mt-4">
            {fa.desk.botsLoadFailed}
          </Alert>
        ) : fleet.length === 0 ? (
          <EmptyState
            className="mt-4"
            title={fa.desk.fleetEmptyTitle}
            body={fa.desk.fleetEmptyBody}
            action={
              <Link to={ROUTES.bots} className={buttonClasses({ variant: 'secondary', size: 'sm' })}>
                {fa.nav.bots}
              </Link>
            }
          />
        ) : (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {fleet.map((bot) => (
              <FleetCard
                key={bot.id}
                bot={bot}
                now={now}
                events={bot.id === leadBot?.id ? leadEvents : EMPTY_EVENTS}
                isLead={bot.id === leadBot?.id}
                canReadAudit={canReadAudit}
              />
            ))}
          </div>
        )}
      </Card>

      <Card as="section" className="p-4 sm:p-6">
        <SectionHeader
          title={fa.desk.feedTitle}
          subtitle={fa.desk.feedSubtitle}
          actions={
            <span className="micro-label hidden text-ink-faint sm:inline">{fa.desk.feedCapNote}</span>
          }
        />

        {auditResource.isLoading && !auditResource.data ? (
          <div className="mt-4 space-y-3" aria-busy="true">
            {Array.from({ length: 5 }, (_, index) => (
              <Skeleton key={index} className="h-9" />
            ))}
          </div>
        ) : auditResource.error && !auditResource.data ? (
          <Alert tone="error" className="mt-4">
            {fa.desk.feedLoadFailed}
          </Alert>
        ) : feed.length === 0 ? (
          <EmptyState
            className="mt-4"
            title={canReadAudit ? fa.desk.feedEmptyTitle : fa.desk.feedNoAccessTitle}
            body={canReadAudit ? fa.desk.feedEmptyBody : fa.desk.auditNoAccess}
          />
        ) : (
          <ul className="mt-4 divide-y divide-line">
            {feed.map(({ event, botName }) => (
              <li
                key={event.id}
                className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2.5 first:pt-0 last:pb-0"
              >
                <span
                  className="num w-16 shrink-0 whitespace-nowrap pt-0.5 text-xs text-ink-faint"
                  title={dateTimeText(event.occurredAt)}
                >
                  {timeText(event.occurredAt)}
                </span>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <Badge tone={auditTone(event.eventType)}>
                      {auditEventLabel(event.eventType)}
                    </Badge>
                    <span className="truncate text-xs font-medium text-ink-soft">{botName}</span>
                    {event.symbol && (
                      <span className="num ms-auto text-xs text-ink-faint" dir="ltr">
                        {event.symbol}
                      </span>
                    )}
                  </div>

                  <p
                    className="mt-1 line-clamp-2 text-xs leading-relaxed text-ink-muted"
                    title={event.summary}
                  >
                    {event.summary}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

/** One bot in the fleet strip, with the lead (first Active) bot's audit tail attached. */
function FleetCard({
  bot,
  now,
  events,
  isLead,
  canReadAudit,
}: {
  bot: BotSummary
  now: number
  events: BotAuditEvent[]
  isLead: boolean
  canReadAudit: boolean
}) {
  return (
    <Card as="article" className="flex min-w-0 flex-col p-4">
      <div className="flex items-start justify-between gap-2">
        <Link
          to={botMonitorPath(bot.id)}
          title={bot.name}
          className="min-w-0 truncate text-sm font-semibold text-ink transition-colors hover:text-accent"
        >
          {bot.name}
        </Link>
        <BotStatusBadge status={bot.status} />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
        <span className="num" dir="ltr">
          {bot.symbol}
        </span>
        <span aria-hidden="true" className="text-ink-faint">
          ·
        </span>
        <span className="num">{bot.interval}</span>

        {bot.openPositionCount > 0 && (
          <Badge tone="accent">{`${countText(bot.openPositionCount)} ${fa.bots.openPositions}`}</Badge>
        )}

        {bot.isBlockedByKillSwitch && (
          <Badge tone="danger">{fa.killSwitches.stateEngaged}</Badge>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between gap-2 text-xs text-ink-faint">
        <span>{fa.bots.colLastTick}</span>
        <span className="num text-ink-muted">
          {bot.lastTickAt ? relativeAge(bot.lastTickAt, now) : fa.bots.neverTicked}
        </span>
      </div>

      {isLead && (
        <div className="mt-3 flex-1 border-t border-line pt-3">
          <p className="micro-label">{fa.desk.timelineLabel}</p>

          {events.length === 0 ? (
            <p className="mt-2 text-xs leading-relaxed text-ink-faint">
              {canReadAudit ? fa.desk.noAuditEvents : fa.desk.auditNoAccess}
            </p>
          ) : (
            <ol className="mt-2 space-y-2 border-s border-line ps-3">
              {events.map((event) => (
                <li key={event.id} className="relative min-w-0">
                  <span
                    aria-hidden="true"
                    className={`absolute top-1.5 size-1.5 rounded-full ${auditDotClass(event.eventType)}`}
                    // A negative logical inset: the dot marks the rail drawn by the list's border-s.
                    style={{ insetInlineStart: '-1rem' }}
                  />

                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-[0.6875rem] font-medium text-ink-soft">
                      {auditEventLabel(event.eventType)}
                    </span>
                    <span className="num shrink-0 text-[0.6875rem] text-ink-faint">
                      {relativeAge(event.occurredAt, now)}
                    </span>
                  </div>

                  <p
                    className="mt-0.5 line-clamp-1 text-[0.6875rem] leading-relaxed text-ink-muted"
                    title={event.summary}
                  >
                    {event.summary}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </Card>
  )
}

/** Score with a fixed three decimals and an explicit sign, so a sign flip is visible at a glance. */
function signedScore(score: number): string {
  if (!Number.isFinite(score)) return '—'
  const magnitude = Math.abs(score).toFixed(3)
  return score < 0 ? `-${magnitude}` : score > 0 ? `+${magnitude}` : magnitude
}

/** The numeric score plus a magnitude bar, scaled against the best score on the board. */
function ScoreMeter({ score, max }: { score: number; max: number }) {
  const share = max > 0 ? Math.abs(score) / max : 0
  const tone =
    score > 0 ? 'text-success-ink' : score < 0 ? 'text-danger-ink' : 'text-ink-muted'
  const bar = score > 0 ? 'bg-success' : score < 0 ? 'bg-danger' : 'bg-line-strong'

  return (
    <div className="flex items-center gap-2.5">
      <span className={`num w-16 text-end text-sm font-medium ${tone}`}>{signedScore(score)}</span>

      <span
        aria-hidden="true"
        className="h-1.5 w-12 shrink-0 overflow-hidden rounded-full bg-surface-muted"
      >
        <span
          className={`block h-full rounded-full ${bar}`}
          style={{ width: `${score === 0 ? 0 : Math.max(5, share * 100)}%` }}
        />
      </span>
    </div>
  )
}

/**
 * Relative age in Persian prose, Latin digits.
 *
 * ScannerPage carries the same shape as a private helper. It is repeated rather than imported
 * because that one is not exported and the page is outside this task's scope; the unit words are
 * still the shared dictionary's, so only the threshold logic is duplicated.
 */
function relativeAge(iso: string | null | undefined, now: number): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'

  const seconds = Math.max(0, Math.floor((now - then) / 1000))
  if (seconds < 60) return `${countText(seconds)} ${fa.desk.secondsAgo}`

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${countText(minutes)} ${fa.scanner.minutesAgo}`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${countText(hours)} ${fa.scanner.hoursAgo}`

  return `${countText(Math.floor(hours / 24))} ${fa.scanner.daysAgo}`
}

function auditStamp(event: BotAuditEvent): number {
  const parsed = Date.parse(event.occurredAt)
  return Number.isNaN(parsed) ? 0 : parsed
}

type BadgeTone = 'neutral' | 'accent' | 'success' | 'warn' | 'danger'

/** Event tone follows the causal chain: refusals and faults red, a completed fill green. */
function auditTone(eventType: BotAuditEventTypeName): BadgeTone {
  switch (eventType) {
    case 'BotFaulted':
    case 'KillSwitchEngaged':
    case 'OrderRejected':
      return 'danger'
    case 'RiskEvaluated':
      return 'warn'
    case 'FillRecorded':
    case 'PositionOpened':
    case 'PositionClosed':
    case 'OrderAcknowledged':
      return 'success'
    case 'ModelConsulted':
    case 'DecisionRecorded':
      return 'accent'
    default:
      return 'neutral'
  }
}

/** The timeline dot, matching the badge tone without drawing a second pill. */
function auditDotClass(eventType: BotAuditEventTypeName): string {
  switch (auditTone(eventType)) {
    case 'danger':
      return 'bg-danger'
    case 'warn':
      return 'bg-warn'
    case 'success':
      return 'bg-success'
    case 'accent':
      return 'bg-accent'
    default:
      return 'bg-line-strong'
  }
}
