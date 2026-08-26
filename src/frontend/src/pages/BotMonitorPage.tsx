import { useCallback, useMemo, useRef, useState, useEffect } from 'react'
import { Link, useParams } from 'react-router'
import { PERMISSIONS, can } from '../auth/permissions'
import { useAuth } from '../auth/AuthContext'
import { Alert } from '../components/ui/Alert'
import { Badge, StatusDot } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Input } from '../components/ui/Input'
import {
  ActionBadge,
  DirectionBadge,
  OperatingModeBadge,
  auditEventLabel,
  normalizeMode,
  reasonCodeLabel,
} from '../components/trading/TradingBadges'
import { fa } from '../i18n/fa'
import { useInterval } from '../lib/useInterval'
import { api } from '../lib/api'
import type { BotAuditEvent, BotAuditEventTypeName, BotDecision, BotDetail, OutcomeReport } from '../lib/apiTypes'
import { ROUTES } from '../routes'
import {
  countText,
  dateTimeText,
  priceText,
  quantityText,
  shareText,
  signedMoneyText,
  timeText,
} from '../lib/tradingFormat'

/**
 * Live monitor for one autonomous bot.
 *
 * Everything on this screen answers "what is the bot doing *right now*": the position it holds and
 * what the market has done to it since entry, whether its heartbeat is alive or stale, what the
 * engine decided on each candle, and every risk event that fired. The whole page polls on a short
 * interval — a monitor that needs a manual refresh is a report, not a monitor.
 *
 * Staleness is judged against the bot's own cadence, not a constant: a 60s-cadence bot silent for
 * three minutes is dead; a 10-minute-cadence bot silent for three minutes is normal. Amber at 2×,
 * red at 4×. The clock ticks once per second so the age readout counts up between polls without
 * waiting for the next fetch.
 */

const POLL_MS = 5_000

type Heartbeat = 'live' | 'stale' | 'dead' | 'idle'

function heartbeatOf(bot: BotDetail, now: number): { state: Heartbeat; ageSeconds: number | null } {
  if (bot.status !== 'Active') return { state: 'idle', ageSeconds: null }

  // The run's heartbeat is the live signal — it updates every tick, including ticks that skip a
  // candle they have already evaluated. `lastTickAt` on the bot row only moves when a candle is
  // actually decided on, so between hourly candles it reads stale while the bot is healthy.
  const candidates = [bot.lastTickAt, bot.currentRun?.lastHeartbeatAt ?? null].filter(Boolean) as string[]
  if (candidates.length === 0) return { state: 'idle', ageSeconds: null }
  const newest = Math.max(...candidates.map(t => Date.parse(t)))
  if (!Number.isFinite(newest)) return { state: 'idle', ageSeconds: null }

  const age = Math.max(0, Math.round((now - newest) / 1000))
  const cadence = Math.max(1, bot.cadenceSeconds)
  if (age > cadence * 4) return { state: 'dead', ageSeconds: age }
  if (age > cadence * 2) return { state: 'stale', ageSeconds: age }
  return { state: 'live', ageSeconds: age }
}

const HEARTBEAT_LABEL: Record<Heartbeat, string> = {
  live: fa.monitor.heartbeatLive,
  stale: fa.monitor.heartbeatStale,
  dead: fa.monitor.heartbeatDead,
  idle: fa.monitor.heartbeatIdle,
}

const HEARTBEAT_TONE: Record<Heartbeat, 'success' | 'warn' | 'danger' | 'neutral'> = {
  live: 'success',
  stale: 'warn',
  dead: 'danger',
  idle: 'neutral',
}

/** Alert-worthy audit events: anything that blocked, denied, faulted, or engaged. */
const ALERT_EVENTS: BotAuditEventTypeName[] = ['KillSwitchEngaged', 'BotFaulted']

type PollState<T> = {
  data: T | null
  error: string | null
  isLoading: boolean
  refetch: () => void
}

/**
 * A polling resource: fetches immediately and exposes `refetch`, which `useInterval` calls at the
 * monitor cadence. Deliberately not `useResource` — that one treats a fetcher identity change as a
 * reload signal, which fights a polling page where the callback closes over fresh values each tick.
 */
function usePolled<T>(fetcher: (signal: AbortSignal) => Promise<T>): PollState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const inFlightRef = useRef(false)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const refetch = useCallback(() => {
    // Skip while one is in flight: a slow response must never stack duplicates behind itself.
    if (inFlightRef.current) return
    inFlightRef.current = true

    const controller = new AbortController()
    fetcherRef.current(controller.signal)
      .then(data => {
        setData(data)
        setError(null)
        setIsLoading(false)
      })
      .catch(cause => {
        if (cause instanceof DOMException && cause.name === 'AbortError') return
        setError(cause instanceof Error ? cause.message : String(cause))
        setIsLoading(false)
      })
      .finally(() => {
        inFlightRef.current = false
      })
  }, [])

  useEffect(() => {
    refetch()
  }, [refetch])

  return { data, error, isLoading, refetch }
}

export function BotMonitorPage() {
  const { session } = useAuth()
  const { botId } = useParams<{ botId: string }>()

  const [now, setNow] = useState(() => Date.now())
  const [stopOpen, setStopOpen] = useState(false)
  const [stopReason, setStopReason] = useState('')

  const fetchBot = useCallback(
    (signal?: AbortSignal) => (botId ? api.bots.byId(botId, signal) : Promise.reject(new Error('no id'))),
    [botId],
  )
  const botResource = usePolled(fetchBot)

  const fetchDecisions = useCallback(
    (signal?: AbortSignal) =>
      botId
        ? api.botHistory.decisions(botId, { pageNumber: 1, pageSize: 20 }, {}, signal)
        : Promise.reject(new Error('no id')),
    [botId],
  )
  const decisions = usePolled(fetchDecisions)

  const fetchAudit = useCallback(
    (signal?: AbortSignal) =>
      botId ? api.botHistory.audit(botId, { pageNumber: 1, pageSize: 30 }, signal) : Promise.reject(new Error('no id')),
    [botId],
  )
  const audit = usePolled(fetchAudit)

  const fetchOutcomes = useCallback(
    (signal?: AbortSignal) =>
      botId
        ? api.outcomes.forBot(botId, signal)
        : Promise.reject(new Error('no id')),
    [botId],
  )
  const outcomes = usePolled(fetchOutcomes)

  const canStop = can(session, PERMISSIONS.botStop)
  const bot = botResource.data

  useInterval(() => setNow(Date.now()), 1_000)
  useInterval(() => botResource.refetch(), POLL_MS, !!botId)
  useInterval(() => decisions.refetch(), POLL_MS, !!botId)
  useInterval(() => audit.refetch(), POLL_MS, !!botId)
  useInterval(() => outcomes.refetch(), POLL_MS, !!botId)

  const stop = useCallback(async () => {
    if (!botId || !stopReason.trim()) return
    await api.bots.stop(botId, { reason: stopReason.trim() })
    setStopOpen(false)
    setStopReason('')
    botResource.refetch()
  }, [botId, stopReason, botResource])

  if (!botId)
    return (
      <div className="space-y-4">
        <BackLink />
        <Alert tone="warn">{fa.botDetail.notFound}</Alert>
      </div>
    )

  if (botResource.error && !bot)
    return (
      <div className="space-y-4">
        <BackLink />
        <Alert tone="error">{botResource.error}</Alert>
      </div>
    )

  if (!bot)
    return (
      <div className="space-y-4">
        <BackLink />
        <Alert tone="info">{fa.common.loading}</Alert>
      </div>
    )

  const heartbeat = heartbeatOf(bot, now)
  const position = bot.openPositions[0]
  const alerts = (audit.data?.items ?? []).filter(e => ALERT_EVENTS.includes(e.eventType))
  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <div className="min-w-0 space-y-1">
          <BackLink />
          <h1 className="text-[1.375rem] font-semibold sm:text-2xl">
            {fa.monitor.title}: {bot.name}
          </h1>
          <p className="text-sm text-ink-muted latin" dir="ltr">
            {bot.symbol} · {bot.interval}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <OperatingModeBadge mode={normalizeMode(bot.operatingMode)} />
          <HeartbeatBadge heartbeat={heartbeat.state} ageSeconds={heartbeat.ageSeconds} />
          {canStop && bot.status === 'Active' && (
            <Button variant="danger" size="sm" onClick={() => setStopOpen(true)}>
              {fa.bots.stop}
            </Button>
          )}
        </div>
      </div>

      {/* Health banner */}
      {bot.status === 'Faulted' && (
        <Alert tone="error" title={fa.monitor.faultedTitle}>
          {bot.statusReason ?? fa.monitor.faultedBody}
        </Alert>
      )}
      {bot.isBlockedByKillSwitch && (
        <Alert tone="warn" title={fa.trading.killSwitchBlocked}>
          {bot.statusReason ?? ''}
        </Alert>
      )}
      {heartbeat.state === 'stale' && bot.status === 'Active' && (
        <Alert tone="warn" title={fa.monitor.staleTitle}>
          {fa.monitor.staleBody(heartbeat.ageSeconds ?? 0)}
        </Alert>
      )}
      {heartbeat.state === 'dead' && bot.status === 'Active' && (
        <Alert tone="error" title={fa.monitor.deadTitle}>
          {fa.monitor.deadBody(heartbeat.ageSeconds ?? 0)}
        </Alert>
      )}

      {/* Position + run */}
      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="micro-label">{fa.monitor.positionLabel}</h2>
        {!position ? (
          <p className="mt-2 text-sm text-ink-faint">{fa.monitor.noPosition}</p>
        ) : (
          <PositionCard position={position} />
        )}

        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-line pt-4 text-sm sm:grid-cols-4">
          <Metric label={fa.monitor.realizedPnl}>
            <span className={`num ${bot.realizedPnl >= 0 ? 'text-success' : 'text-danger'}`}>
              {signedMoneyText(bot.realizedPnl)}
            </span>
          </Metric>
          <Metric label={fa.botDetail.tickCount}>
            <span className="num">{countText(bot.currentRun?.tickCount ?? 0)}</span>
          </Metric>
          <Metric label={fa.monitor.lastCandle}>
            <span className="num text-xs">{dateTimeText(bot.lastEvaluatedCandleOpenTime)}</span>
          </Metric>
          <Metric label={fa.trading.minimumConfidence}>
            <span className="num">{shareText(bot.minimumConfidence)}</span>
          </Metric>
        </dl>
      </section>

      {/* Self-learning report */}
      {outcomes.data && outcomes.data.sampleSize > 0 && (
        <section className="space-y-3 rounded-xl border border-line bg-surface p-5">
          <h2 className="micro-label">{fa.monitor.outcomesLabel}</h2>
          <p className="text-xs text-ink-muted">{fa.monitor.outcomesNote}</p>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
            <Metric label={fa.monitor.sampleSize}>
              <span className="num font-medium">{countText(outcomes.data.sampleSize)}</span>
            </Metric>
            <Metric label={fa.monitor.winRate}>
              <span className="num font-medium">
                {shareText(outcomes.data.wins / Math.max(1, outcomes.data.sampleSize))}
              </span>
            </Metric>
            <Metric label={fa.monitor.totalPnl}>
              <span className={`num ${outcomes.data.totalRealizedPnl >= 0 ? 'text-success' : 'text-danger'}`}>
                {signedMoneyText(outcomes.data.totalRealizedPnl)}
              </span>
            </Metric>
            <Metric label={fa.monitor.avgPnl}>
              <span className={`num ${outcomes.data.averageRealizedPnl >= 0 ? 'text-success' : 'text-danger'}`}>
                {signedMoneyText(outcomes.data.averageRealizedPnl)}
              </span>
            </Metric>
          </dl>

          {/* Calibration: bucket win rate should rise with the bucket center. */}
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line">
                <th scope="col" className="micro-label py-2 text-start">{fa.monitor.bucket}</th>
                <th scope="col" className="micro-label py-2 text-end">{fa.monitor.tradesCol}</th>
                <th scope="col" className="micro-label py-2 text-end">{fa.monitor.winRateCol}</th>
                <th scope="col" className="micro-label py-2 text-end">{fa.monitor.pnlCol}</th>
              </tr>
            </thead>
            <tbody>
              {outcomes.data.calibrationBuckets.map(b => (
                <tr key={b.lower} className="border-b border-line/50 last:border-0">
                  <td className="py-2 num" dir="ltr">
                    {b.lower.toFixed(2)}–{Math.min(b.upper, 1).toFixed(2)}
                  </td>
                  <td className="py-2 num text-end">{countText(b.trades)}</td>
                  <td className="py-2 num text-end">
                    {b.trades === 0 ? '—' : shareText(b.wins / b.trades)}
                  </td>
                  <td className={`py-2 num text-end ${b.totalPnl >= 0 ? 'text-success' : 'text-danger'}`}>
                    {b.trades === 0 ? '—' : signedMoneyText(b.totalPnl)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Alerts */}
      {alerts.length > 0 && (
        <section className="space-y-3">
          <h2 className="micro-label">{fa.monitor.alertsLabel}</h2>
          <div className="space-y-2">
            {alerts.slice(0, 5).map(a => (
              <Alert key={a.id} tone={a.eventType === 'BotFaulted' ? 'error' : 'warn'}>
                <span className="font-semibold me-2">{auditEventLabel(a.eventType)}</span>
                {a.summary}
                <span className="ms-auto num text-xs text-ink-faint">{timeText(a.occurredAt)}</span>
              </Alert>
            ))}
          </div>
        </section>
      )}

      {/* Decision stream */}
      <section className="space-y-3">
        <h2 className="micro-label">{fa.monitor.decisionsLabel}</h2>
        <DecisionsTable rows={decisions.data?.items ?? []} isLoading={decisions.isLoading && !decisions.data} />
      </section>

      {/* Stop dialog */}
      <ConfirmDialog
        isOpen={stopOpen}
        onClose={() => {
          setStopOpen(false)
          setStopReason('')
        }}
        onConfirm={stop}
        title={fa.bots.confirmStopTitle}
        confirmLabel={fa.bots.stop}
        tone="danger"
        body={
          <div className="space-y-4">
            <p>{fa.bots.confirmStopBody}</p>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-ink-soft">
                {fa.bots.reason} <span className="text-danger">*</span>
              </label>
              <Input value={stopReason} onChange={e => setStopReason(e.target.value)} placeholder={fa.bots.reasonHint} />
            </div>
          </div>
        }
      />
    </div>
  )
}

// ── pieces ────────────────────────────────────────────────────────────────────────────────────────

function BackLink() {
  return (
    <Link to={ROUTES.bots} className="inline-flex items-center gap-1.5 text-xs text-ink-muted hover:text-accent">
      <span aria-hidden="true">→</span>
      {fa.botDetail.back}
    </Link>
  )
}

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="micro-label">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function HeartbeatBadge({ heartbeat, ageSeconds }: { heartbeat: Heartbeat; ageSeconds: number | null }) {
  return (
    <Badge tone={HEARTBEAT_TONE[heartbeat]}>
      <StatusDot tone={HEARTBEAT_TONE[heartbeat]} pulse={heartbeat === 'live'} />
      {HEARTBEAT_LABEL[heartbeat]}
      {ageSeconds !== null && heartbeat !== 'idle' && <span className="num ms-1 opacity-80">({ageSeconds}s)</span>}
    </Badge>
  )
}

type PositionView = BotDetail['openPositions'][number]

function PositionCard({ position }: { position: PositionView }) {
  const tpDistance =
    position.takeProfitPrice !== null && position.averageEntryPrice !== 0
      ? ((position.takeProfitPrice - position.averageEntryPrice) / position.averageEntryPrice) * 100
      : null

  return (
    <div className="mt-3 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <DirectionBadge direction={position.direction} />
        <span className="num text-lg font-semibold">{quantityText(position.quantity)}</span>
        <span className="text-xs latin" dir="ltr">
          @ {priceText(position.averageEntryPrice)}
        </span>
        <span
          className={`ms-auto num text-xl font-semibold ${
            (position.unrealizedPnl ?? 0) >= 0 ? 'text-success' : 'text-danger'
          }`}
        >
          {signedMoneyText(position.unrealizedPnl)}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
        <Metric label={fa.botDetail.markPrice}>
          <span className="num font-medium">{priceText(position.lastMarkPrice)}</span>
        </Metric>
        <Metric label={fa.trading.takeProfitPrice}>
          <span className="num text-success">
            {priceText(position.takeProfitPrice)}
            {tpDistance !== null && <span className="ms-1 text-xs opacity-70">(+{tpDistance.toFixed(2)}%)</span>}
          </span>
        </Metric>
        <Metric label={fa.trading.stopLossPrice}>
          <span className="num text-danger">{priceText(position.stopLossPrice)}</span>
        </Metric>
        <Metric label={fa.botDetail.barsHeld}>
          <span className="num">{countText(position.barsHeld)}</span>
        </Metric>
      </div>

      {position.lastMarkedAt && (
        <p className="text-xs text-ink-faint">
          {fa.monitor.markedAt}: <span className="num">{timeText(position.lastMarkedAt)}</span>
        </p>
      )}
    </div>
  )
}

function DecisionsTable({ rows, isLoading }: { rows: BotDecision[]; isLoading: boolean }) {
  const columns: Column<BotDecision>[] = [
    {
      key: 'candle',
      header: fa.botDetail.colCandle,
      cell: d => <span className="num text-xs">{dateTimeText(d.candleOpenTime)}</span>,
    },
    {
      key: 'action',
      header: fa.botDetail.colAction,
      cell: d => (
        <div className="flex items-center gap-1.5">
          <ActionBadge action={d.action} />
          {d.action !== 'Hold' && <DirectionBadge direction={d.direction} />}
        </div>
      ),
    },
    {
      key: 'confidence',
      header: fa.trading.confidence,
      cell: d => <span className="num">{shareText(d.confidence)}</span>,
    },
    {
      key: 'reason',
      header: fa.botDetail.colReason,
      cell: d => <span className="text-xs">{reasonCodeLabel(d.reasonCode) ?? d.reasonCode}</span>,
    },
    {
      key: 'at',
      header: fa.monitor.decidedAt,
      cell: d => <span className="num text-xs">{timeText(d.createdAt)}</span>,
    },
  ]

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={r => r.id}
      isLoading={isLoading}
      emptyTitle={fa.monitor.noDecisions}
      skeletonRows={4}
    />
  )
}
