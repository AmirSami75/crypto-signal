import { useCallback, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router'
import { PERMISSIONS, can } from '../auth/permissions'
import { useAuth } from '../auth/AuthContext'
import { Alert } from '../components/ui/Alert'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Input } from '../components/ui/Input'
import {
  ActionBadge,
  DirectionBadge,
  IntentStatusBadge,
  OperatingModeBadge,
  PositionStatusBadge,
  auditEventLabel,
  closeReasonLabel,
  normalizeMode,
  reasonCodeLabel,
  riskCheckLabel,
} from '../components/trading/TradingBadges'
import { fa } from '../i18n/fa'
import { TearsheetPanel } from '../components/trading/TearsheetPanel'
import { api } from '../lib/api'
import type {
  BotAuditEvent,
  BotDecision,
  BotPosition,
  OperatingModeName,
  OrderIntent,
  TradingPageQuery,
} from '../lib/apiTypes'
import { ROUTES, botMonitorPath } from '../routes'
import {
  countText,
  dateTimeText,
  digestText,
  moneyText,
  priceText,
  quantityText,
  ratioText,
  shareText,
  signedMoneyText,
  timeText,
} from '../lib/tradingFormat'
import { useResource } from '../lib/useResource'

/**
 * One bot's detail screen: the open position, and the read side of its causal chain.
 *
 * The four history tabs — decisions, orders, positions, audit — are one component each because they
 * share nothing but the page query; merging them into a generic "history table" would couple four
 * wire shapes that evolve separately. Each gates itself on its own permission, so an operator holding
 * only `Bot.Get` sees the overview and none of the chain.
 *
 * The per-bot kill switch sits at the foot of the overview tab rather than in the sidebar of actions:
 * engaging it is the loudest thing this screen can do, and it belongs next to the position it would
 * strand, with the scope note from the safety policy attached.
 */

const TABS = ['overview', 'decisions', 'orders', 'positions', 'audit', 'tearsheet'] as const
type Tab = (typeof TABS)[number]

const PAGE_SIZE = 10

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="micro-label">{label}</p>
      <div className="text-sm text-ink">{children}</div>
    </div>
  )
}

export function BotDetailPage() {
  const { session } = useAuth()
  const { botId } = useParams<{ botId: string }>()

  const [tab, setTab] = useState<Tab>('overview')
  const [page, setPage] = useState(1)
  const [killSwitchOpen, setKillSwitchOpen] = useState(false)
  const [killSwitchReason, setKillSwitchReason] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  const fetcher = useCallback(
    (signal?: AbortSignal) => (botId ? api.bots.byId(botId, signal) : Promise.reject(new Error('no id'))),
    [botId],
  )
  // The detail payload carries the current run and open positions; a tick changes both, so polling
  // keeps the heartbeat honest without a manual refresh.
  const { data: bot, error, isLoading, refetch } = useResource(fetcher)

  const canEngageKillSwitch = can(session, PERMISSIONS.killSwitchEngage)
  const canSeeDecisions = can(session, PERMISSIONS.botHistoryGetDecisions)
  const canSeeOrders = can(session, PERMISSIONS.botHistoryGetOrders)
  const canSeePositions = can(session, PERMISSIONS.botHistoryGetPositions)
  const canSeeAudit = can(session, PERMISSIONS.botHistoryGetAudit)

  const visibleTabs = TABS.filter(t => {
    if (t === 'decisions') return canSeeDecisions
    if (t === 'orders') return canSeeOrders
    if (t === 'positions') return canSeePositions
    if (t === 'audit') return canSeeAudit
    return true
  })

  const engageForBot = useCallback(async () => {
    if (!botId || !killSwitchReason.trim()) return
    await api.killSwitches.engage({
      scope: 'Bot',
      scopeBotId: botId,
      reason: killSwitchReason.trim(),
    })
    setKillSwitchOpen(false)
    setKillSwitchReason('')
    setNotice(fa.killSwitches.engagedSuccess)
    refetch()
  }, [botId, killSwitchReason, refetch])

  if (isLoading && !bot) return <Alert tone="info">{fa.common.loading}</Alert>

  if (error && !bot)
    return (
      <div className="space-y-4">
        <Link to={ROUTES.bots} className="inline-flex items-center gap-2 text-sm text-accent hover:underline">
          {fa.botDetail.back}
        </Link>
        <Alert tone="error">{error}</Alert>
      </div>
    )

  if (!bot)
    return (
      <div className="space-y-4">
        <Link to={ROUTES.bots} className="inline-flex items-center gap-2 text-sm text-accent hover:underline">
          {fa.botDetail.back}
        </Link>
        <Alert tone="warn">{fa.botDetail.notFound}</Alert>
      </div>
    )

  const mode: OperatingModeName | string = normalizeMode(bot.operatingMode)

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <div className="min-w-0 space-y-1">
          <Link to={ROUTES.bots} className="inline-flex items-center gap-1.5 text-xs text-ink-muted hover:text-accent">
            <span aria-hidden="true">→</span>
            {fa.botDetail.back}
          </Link>
          <h1 className="text-[1.375rem] font-semibold sm:text-2xl">{bot.name}</h1>
          <p className="text-sm text-ink-muted latin" dir="ltr">
            {bot.symbol} · {bot.interval}
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {/* Operating mode — prominent on every bot screen */}
          <OperatingModeBadge mode={mode} />
          <Badge tone={bot.status === 'Active' ? 'success' : bot.status === 'Faulted' ? 'danger' : 'neutral'}>
            {fa.trading.botStatus[bot.status] ?? bot.status}
          </Badge>
          <Link to={botMonitorPath(bot.id)}>
            <Button variant="outline" size="sm">
              ◉ {fa.monitor.title}
            </Button>
          </Link>
          {canEngageKillSwitch && (
            <Button variant="danger" size="sm" onClick={() => setKillSwitchOpen(true)}>
              {fa.botDetail.engageForBot}
            </Button>
          )}
        </div>
      </div>

      {bot.isBlockedByKillSwitch && (
        <Alert tone="error">
          {fa.trading.killSwitchBlocked}
          {bot.statusReason ? ` — ${bot.statusReason}` : ''}
        </Alert>
      )}

      {notice && <Alert tone="success">{notice}</Alert>}

      {/* Tabs */}
      <div role="tablist" className="flex flex-wrap gap-1 rounded-xl border border-line bg-surface p-1">
        {visibleTabs.map(t => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            onClick={() => {
              setTab(t)
              setPage(1)
            }}
            className={[
              'rounded-lg px-3.5 py-2 text-sm transition-colors',
              tab === t ? 'bg-surface-muted font-medium text-ink' : 'text-ink-muted hover:text-ink',
            ].join(' ')}
          >
            {t === 'overview' && fa.botDetail.tabOverview}
            {t === 'decisions' && fa.botDetail.tabDecisions}
            {t === 'orders' && fa.botDetail.tabOrders}
            {t === 'positions' && fa.botDetail.tabPositions}
            {t === 'audit' && fa.botDetail.tabAudit}
            {t === 'tearsheet' && fa.botDetail.tabTearsheet}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <OverviewTab bot={bot} />
      )}
      {tab === 'decisions' && botId && canSeeDecisions && <DecisionsTab botId={botId} page={page} onPageChange={setPage} />}
      {tab === 'orders' && botId && canSeeOrders && <OrdersTab botId={botId} page={page} onPageChange={setPage} />}
      {tab === 'positions' && botId && canSeePositions && <PositionsTab botId={botId} page={page} onPageChange={setPage} />}
      {tab === 'audit' && botId && canSeeAudit && <AuditTab botId={botId} page={page} onPageChange={setPage} />}
      {tab === 'tearsheet' && botId && <TearsheetPanel botId={botId} />}

      {/* Per-bot kill switch confirmation */}
      <ConfirmDialog
        isOpen={killSwitchOpen}
        onClose={() => {
          setKillSwitchOpen(false)
          setKillSwitchReason('')
        }}
        onConfirm={engageForBot}
        title={fa.killSwitches.confirmEngageTitle}
        confirmLabel={fa.killSwitches.engageButton}
        tone="danger"
        body={
          <div className="space-y-4">
            <p>{fa.killSwitches.scopeNote}</p>
            <div className="flex items-center gap-2">
              <span className="text-sm text-ink-soft">{fa.trading.modeLabel}:</span>
              <OperatingModeBadge mode={mode} />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-ink-soft">
                {fa.killSwitches.reason} <span className="text-danger">*</span>
              </label>
              <Input
                value={killSwitchReason}
                onChange={e => setKillSwitchReason(e.target.value)}
                placeholder={fa.killSwitches.reasonHint}
              />
            </div>
          </div>
        }
      />
    </div>
  )
}

// ─── Overview ─────────────────────────────────────────────────────────────────────────────────────

type BotDetailData = Awaited<ReturnType<typeof api.bots.byId>>

function OverviewTab({ bot }: { bot: BotDetailData }) {
  const run = bot.currentRun

  return (
    <div className="space-y-5">
      {/* Open positions */}
      <section className="space-y-3">
        <h2 className="micro-label">{fa.botDetail.positionsLabel}</h2>
        {bot.openPositions.length === 0 ? (
          <p className="text-sm text-ink-faint">{fa.botDetail.noPositions}</p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {bot.openPositions.map(p => (
              <div key={p.id} className="space-y-3 rounded-xl border border-line bg-surface p-4">
                <div className="flex items-center gap-2">
                  <DirectionBadge direction={p.direction} />
                  <PositionStatusBadge status={p.status} />
                  <OperatingModeBadge mode={normalizeMode(p.operatingMode)} />
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
                  <Stat label={fa.botDetail.averageEntry}>
                    <span className="num">{priceText(p.averageEntryPrice)}</span>
                  </Stat>
                  <Stat label={fa.trading.quantity}>
                    <span className="num">{quantityText(p.quantity)}</span>
                  </Stat>
                  <Stat label={fa.trading.takeProfitPrice}>
                    <span className="num text-success">{priceText(p.takeProfitPrice)}</span>
                  </Stat>
                  <Stat label={fa.trading.stopLossPrice}>
                    <span className="num text-danger">{priceText(p.stopLossPrice)}</span>
                  </Stat>
                  <Stat label={fa.trading.unrealizedPnl}>
                    <span className={`num ${((p.unrealizedPnl ?? 0) >= 0 ? 'text-success' : 'text-danger')}`}>
                      {signedMoneyText(p.unrealizedPnl)}
                    </span>
                  </Stat>
                  <Stat label={fa.botDetail.markPrice}>
                    <span className="num">{priceText(p.lastMarkPrice)}</span>
                  </Stat>
                  <Stat label={fa.botDetail.barsHeld}>
                    <span className="num">{countText(p.barsHeld)}</span>
                  </Stat>
                  <Stat label={fa.botDetail.openedAt}>
                    <span className="num">{dateTimeText(p.openedAt)}</span>
                  </Stat>
                  <Stat label={fa.botDetail.maxAdverseExcursion}>
                    <span className="num">{priceText(p.maxAdverseExcursion)}</span>
                  </Stat>
                </div>
              </div>
            ))}
          </div>
        )}
        <p className="text-xs text-ink-faint">
          {fa.botDetail.closedPositionCount}: <span className="num">{countText(bot.closedPositionCount)}</span>
          {' · '}
          {fa.bots.colPnl}: <span className={`num ${bot.realizedPnl >= 0 ? 'text-success' : 'text-danger'}`}>{signedMoneyText(bot.realizedPnl)}</span>
        </p>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Current run */}
        <section className="space-y-3 rounded-xl border border-line bg-surface p-4">
          <h2 className="micro-label">{fa.botDetail.runLabel}</h2>
          {!run ? (
            <p className="text-sm text-ink-faint">{fa.botDetail.noRun}</p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                <Stat label={fa.botDetail.tickCount}>
                  <span className="num">{countText(run.tickCount)}</span>
                </Stat>
                <Stat label={fa.botDetail.decisionCount}>
                  <span className="num">{countText(run.decisionCount)}</span>
                </Stat>
                <Stat label={fa.botDetail.orderCount}>
                  <span className="num">{countText(run.orderCount)}</span>
                </Stat>
                <Stat label={fa.botDetail.errorCount}>
                  <span className={`num ${run.errorCount > 0 ? 'text-danger' : ''}`}>
                    {countText(run.errorCount)}
                  </span>
                </Stat>
              </div>
              <p className="text-xs text-ink-faint">
                {fa.botDetail.lastHeartbeat}:{' '}
                <span className="num">{run.lastHeartbeatAt ? timeText(run.lastHeartbeatAt) : '—'}</span>
              </p>
              {run.lastError && (
                <Alert tone="warn">
                  <span className="line-clamp-2 num" dir="ltr">
                    {run.lastError}
                  </span>
                </Alert>
              )}
            </>
          )}
        </section>

        {/* Configuration */}
        <section className="space-y-3 rounded-xl border border-line bg-surface p-4">
          <h2 className="micro-label">{fa.botDetail.configLabel}</h2>
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            <Stat label={fa.trading.takeProfitPercent}>
              <span className="num">{`${bot.takeProfitPercent}%`}</span>
            </Stat>
            <Stat label={fa.trading.stopLossPercent}>
              <span className="num">{`${bot.stopLossPercent}%`}</span>
            </Stat>
            {(bot as any).takeProfitAtrMultiple != null && (
              <Stat label={(fa.trading as any).takeProfitAtrMultiple ?? 'ATR حد سود'}>
                <span className="num">{`${(bot as any).takeProfitAtrMultiple}× ATR`}</span>
              </Stat>
            )}
            {(bot as any).stopLossAtrMultiple != null && (
              <Stat label={(fa.trading as any).stopLossAtrMultiple ?? 'ATR حد ضرر'}>
                <span className="num">{`${(bot as any).stopLossAtrMultiple}× ATR`}</span>
              </Stat>
            )}
            <Stat label={fa.trading.allowShort}>
              {bot.allowShort ? fa.common.active : fa.common.inactive}
            </Stat>
            <Stat label={fa.bots.quoteNotionalPerTrade}>
              <span className="num">{moneyText(bot.quoteNotionalPerTrade)}</span>
            </Stat>
            <Stat label={fa.bots.leverage}>
              <span className="num">{`${bot.leverage}${fa.overview.leverageUnit}`}</span>
            </Stat>
            <Stat label={fa.bots.estimatedNotional}>
              <span className="num">{moneyText(bot.estimatedNotional)}</span>
            </Stat>
            <Stat label={fa.bots.estimatedMargin}>
              <span className="num">{moneyText(bot.estimatedMargin)}</span>
            </Stat>
            <Stat label={fa.trading.minimumConfidence}>
              <span className="num">{shareText(bot.minimumConfidence)}</span>
            </Stat>
            <Stat label={fa.bots.cadenceSeconds}>
              <span className="num">{`${bot.cadenceSeconds}s`}</span>
            </Stat>
          </div>

          <h3 className="micro-label pt-2">{fa.botDetail.limitsLabel}</h3>
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            <Stat label={fa.bots.maxOrderNotional}>
              <span className="num">{moneyText(bot.maxOrderNotional)}</span>
            </Stat>
            <Stat label={fa.bots.maxPositionNotional}>
              <span className="num">{moneyText(bot.maxPositionNotional)}</span>
            </Stat>
            <Stat label={fa.bots.maxDailyLoss}>
              <span className="num">{moneyText(bot.maxDailyLoss)}</span>
            </Stat>
            <Stat label={fa.bots.maxDrawdown}>
              <span className="num">{moneyText(bot.maxDrawdown)}</span>
            </Stat>
            <Stat label={fa.bots.maxConcurrentPositions}>
              <span className="num">{countText(bot.maxConcurrentPositions)}</span>
            </Stat>
            <Stat label={fa.bots.maxOrdersPerDay}>
              <span className="num">{countText(bot.maxOrdersPerDay)}</span>
            </Stat>
            <Stat label={fa.bots.maxSlippageBps}>
              <span className="num">{countText(bot.maxSlippageBps)}</span>
            </Stat>
            <Stat label={fa.bots.availableQuoteBalance}>
              {bot.availableQuoteBalance == null ? (
                <span className="text-muted">{fa.bots.notAvailable}</span>
              ) : (
                <span className="num">{moneyText(bot.availableQuoteBalance)}</span>
              )}
            </Stat>
          </div>
          {/* Zero means deny, restated wherever the limits are shown. */}
          <p className="text-xs text-warn-ink">{fa.bots.limitsNote}</p>
        </section>
      </div>
    </div>
  )
}

// ─── Decisions ────────────────────────────────────────────────────────────────────────────────────

function DecisionsTab({
  botId,
  page,
  onPageChange,
}: {
  botId: string
  page: number
  onPageChange: (page: number) => void
}) {
  const fetcher = useCallback(
    (signal?: AbortSignal) =>
      api.botHistory.decisions(botId, { pageNumber: page, pageSize: PAGE_SIZE }, {}, signal),
    [botId, page],
  )
  const { data, error, isLoading, isRefreshing } = useResource(fetcher)
  const rows = data?.items ?? []

  const columns: Column<BotDecision>[] = [
    {
      key: 'candle',
      header: fa.botDetail.colCandle,
      cell: d => <span className="num">{dateTimeText(d.candleOpenTime)}</span>,
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
      key: 'levels',
      header: fa.botDetail.colLevels,
      cell: d =>
        d.entryPrice !== null ? (
          <span className="num text-xs" dir="ltr">
            {priceText(d.entryPrice)} / TP {priceText(d.takeProfitPrice)} / SL {priceText(d.stopLossPrice)}
          </span>
        ) : (
          <span className="text-ink-faint">—</span>
        ),
    },
    {
      key: 'reason',
      header: fa.botDetail.colReason,
      cell: d => (
        <span className="text-xs text-ink-muted">{reasonCodeLabel(d.reasonCode) ?? d.reasonCode}</span>
      ),
    },
    {
      key: 'model',
      header: fa.trading.modelVersion,
      cell: d => (
        <div className="space-y-0.5">
          <span className="num text-xs latin">{digestText(d.modelVersion)}</span>
          {d.usedWildcardModel && (
            <p className="text-[0.6875rem] text-ink-faint">({fa.trading.pooledModel})</p>
          )}
        </div>
      ),
    },
  ]

  return (
    <ListSection
      title={fa.botDetail.decisionsLabel}
      emptyTitle={fa.botDetail.decisionsEmptyTitle}
      emptyBody={fa.botDetail.decisionsEmptyBody}
      columns={columns}
      rows={rows}
      rowKey={r => r.id}
      totalRecords={data?.totalRecords ?? 0}
      page={page}
      pageSize={PAGE_SIZE}
      isLoading={isLoading}
      isRefreshing={isRefreshing}
      error={error}
      onPageChange={onPageChange}
    />
  )
}

// ─── Orders ───────────────────────────────────────────────────────────────────────────────────────

function OrdersTab({
  botId,
  page,
  onPageChange,
}: {
  botId: string
  page: number
  onPageChange: (page: number) => void
}) {
  const fetcher = useCallback(
    (signal?: AbortSignal) => api.botHistory.orders(botId, { pageNumber: page, pageSize: PAGE_SIZE }, signal),
    [botId, page],
  )
  const { data, error, isLoading, isRefreshing } = useResource(fetcher)
  const rows = data?.items ?? []

  return (
    <div className="space-y-4">
      {rows.map(intent => (
        <IntentCard key={intent.id} intent={intent} />
      ))}
      {rows.length === 0 && !isLoading && (
        <Alert tone="info">
          <div className="space-y-1">
            <p className="font-semibold">{fa.botDetail.ordersEmptyTitle}</p>
            <p>{fa.botDetail.ordersEmptyBody}</p>
          </div>
        </Alert>
      )}
      <SimplePagination
        totalRecords={data?.totalRecords ?? 0}
        page={page}
        pageSize={PAGE_SIZE}
        isLoading={isLoading || isRefreshing}
        error={error}
        onPageChange={onPageChange}
      />
    </div>
  )
}

/**
 * An intent renders as a card rather than a table row because it *contains* tables: risk verdict,
 * venue orders, fills. A denied intent is kept on screen deliberately — see `apiTypes.RiskDecision`.
 */
function IntentCard({ intent }: { intent: OrderIntent }) {
  const risk = intent.riskDecision

  return (
    <article className="space-y-3 rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <IntentStatusBadge status={intent.status} />
        <DirectionBadge direction={intent.direction} />
        <OperatingModeBadge mode={normalizeMode(intent.operatingMode)} />
        <span className="ms-auto text-xs text-ink-faint num">{dateTimeText(intent.createdAt)}</span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <Stat label={fa.botDetail.clientOrderId}>
          <span className="num text-xs latin" dir="ltr">
            {digestText(intent.clientOrderId, 12)}
          </span>
        </Stat>
        <Stat label={fa.trading.symbol}>
          <span className="latin" dir="ltr">
            {intent.symbol}
          </span>
        </Stat>
        <Stat label={fa.trading.quantity}>
          <span className="num">{quantityText(intent.quantity)}</span>
        </Stat>
        <Stat label={fa.trading.entryPrice}>
          <span className="num">{priceText(intent.referencePrice)}</span>
        </Stat>
      </div>

      {risk && (
        <div className="space-y-1.5 rounded-lg bg-surface-muted p-3">
          <div className="flex items-center gap-2">
            <span className="micro-label">{fa.botDetail.riskLabel}</span>
            {risk.allowed ? (
              <Badge tone="success">{fa.botDetail.riskAllowed}</Badge>
            ) : (
              <Badge tone="danger">{fa.botDetail.riskDenied}</Badge>
            )}
          </div>
          {!risk.allowed && risk.failedChecks.length > 0 && (
            <ul className="list-disc space-y-0.5 ps-4 text-xs text-danger-ink">
              {risk.failedChecks.map(check => (
                <li key={check}>{riskCheckLabel(check)}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {intent.exchangeOrders.length > 0 && (
        <div className="space-y-2">
          {intent.exchangeOrders.map(order => (
            <div key={order.id} className="space-y-1.5 rounded-lg border border-line p-3">
              <div className="flex flex-wrap items-center gap-2">
                <OrderStatusPill status={order.status} />
                <span className="text-xs text-ink-faint">
                  {fa.botDetail.venueOrderId}:{' '}
                  <span className="num latin" dir="ltr">
                    {order.venueOrderId ?? '—'}
                  </span>
                </span>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
                <span>
                  {fa.trading.quantity}: <span className="num">{quantityText(order.filledQuantity)}</span>
                </span>
                <span>
                  {fa.trading.entryPrice}:{' '}
                  <span className="num">{priceText(order.averageFillPrice)}</span>
                </span>
              </div>
              {order.fills.length > 0 && (
                <details className="text-xs">
                  <summary className="cursor-pointer text-ink-muted hover:text-ink">
                    {fa.botDetail.fills} ({countText(order.fills.length)})
                  </summary>
                  <ul className="mt-1 space-y-0.5 ps-4">
                    {order.fills.map(fill => (
                      <li key={fill.id} className="num">
                        {quantityText(fill.quantity)} @ {priceText(fill.price)} · {timeText(fill.executedAt)}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </article>
  )
}

function OrderStatusPill({ status }: { status: string }) {
  const tone =
    status === 'Filled' ? 'success' : status === 'Rejected' ? 'danger' : status === 'New' ? 'accent' : 'neutral'
  return <Badge tone={tone}>{fa.trading.orderStatus[status] ?? status}</Badge>
}

// ─── Positions ────────────────────────────────────────────────────────────────────────────────────

function PositionsTab({
  botId,
  page,
  onPageChange,
}: {
  botId: string
  page: number
  onPageChange: (page: number) => void
}) {
  const fetcher = useCallback(
    (signal?: AbortSignal) => api.botHistory.positions(botId, { pageNumber: page, pageSize: PAGE_SIZE }, signal),
    [botId, page],
  )
  const { data, error, isLoading, isRefreshing } = useResource(fetcher)
  const rows = data?.items ?? []

  const columns: Column<BotPosition>[] = [
    {
      key: 'direction',
      header: fa.trading.directionLabel,
      cell: p => (
        <div className="flex items-center gap-1.5">
          <DirectionBadge direction={p.direction} />
          <PositionStatusBadge status={p.status} />
        </div>
      ),
    },
    {
      key: 'entry',
      header: fa.botDetail.averageEntry,
      cell: p => <span className="num">{priceText(p.averageEntryPrice)}</span>,
    },
    {
      key: 'exit',
      header: fa.botDetail.averageExit,
      cell: p => <span className="num">{priceText(p.averageExitPrice)}</span>,
    },
    {
      key: 'qty',
      header: fa.trading.quantity,
      cell: p => <span className="num">{quantityText(p.quantity)}</span>,
    },
    {
      key: 'pnl',
      header: fa.bots.colPnl,
      cell: p => (
        <span className={`num ${p.realizedPnl >= 0 ? 'text-success' : 'text-danger'}`}>
          {signedMoneyText(p.realizedPnl)}
        </span>
      ),
    },
    {
      key: 'closeReason',
      header: fa.trading.closeReasonLabel,
      cell: p => <span className="text-xs">{closeReasonLabel(p.closeReason) ?? '—'}</span>,
    },
    {
      key: 'openedAt',
      header: fa.botDetail.openedAt,
      cell: p => <span className="num text-xs">{dateTimeText(p.openedAt)}</span>,
    },
  ]

  return (
    <ListSection
      title={fa.botDetail.tabPositions}
      emptyTitle={fa.botDetail.positionsEmptyTitle}
      emptyBody={fa.botDetail.positionsEmptyBody}
      columns={columns}
      rows={rows}
      rowKey={r => r.id}
      totalRecords={data?.totalRecords ?? 0}
      page={page}
      pageSize={PAGE_SIZE}
      isLoading={isLoading}
      isRefreshing={isRefreshing}
      error={error}
      onPageChange={onPageChange}
    />
  )
}

// ─── Audit ────────────────────────────────────────────────────────────────────────────────────────

function AuditTab({
  botId,
  page,
  onPageChange,
}: {
  botId: string
  page: number
  onPageChange: (page: number) => void
}) {
  const fetcher = useCallback(
    (signal?: AbortSignal) => api.botHistory.audit(botId, { pageNumber: page, pageSize: PAGE_SIZE }, signal),
    [botId, page],
  )
  const { data, error, isLoading, isRefreshing } = useResource(fetcher)
  const rows = data?.items ?? []

  const columns: Column<BotAuditEvent>[] = [
    {
      key: 'event',
      header: fa.botDetail.colEvent,
      cell: e => <span className="text-xs">{auditEventLabel(e.eventType)}</span>,
    },
    {
      key: 'summary',
      header: fa.botDetail.colSummary,
      cell: e => <span className="text-xs text-ink-muted">{e.summary}</span>,
    },
    {
      key: 'sequence',
      header: fa.botDetail.colSequence,
      cell: e => <span className="num text-xs">{countText(e.sequence)}</span>,
    },
    {
      key: 'model',
      header: fa.trading.modelVersion,
      cell: e => (e.modelVersion ? <span className="num text-xs latin">{digestText(e.modelVersion)}</span> : '—'),
    },
    {
      key: 'actor',
      header: fa.botDetail.actor,
      cell: e => <span className="text-xs">{e.actorUserName ?? fa.botDetail.actorSystem}</span>,
    },
    {
      key: 'occurredAt',
      header: fa.botDetail.colOccurredAt,
      cell: e => <span className="num text-xs">{timeText(e.occurredAt)}</span>,
    },
  ]

  return (
    <ListSection
      title={fa.botDetail.auditLabel}
      emptyTitle={fa.botDetail.auditEmptyTitle}
      emptyBody={fa.botDetail.auditEmptyBody}
      columns={columns}
      rows={rows}
      rowKey={r => r.id}
      totalRecords={data?.totalRecords ?? 0}
      page={page}
      pageSize={PAGE_SIZE}
      isLoading={isLoading}
      isRefreshing={isRefreshing}
      error={error}
      onPageChange={onPageChange}
    />
  )
}

// ─── Shared listing shell ─────────────────────────────────────────────────────────────────────────

function ListSection<T>({
  title,
  emptyTitle,
  emptyBody,
  columns,
  rows,
  rowKey,
  totalRecords,
  page,
  pageSize,
  isLoading,
  isRefreshing,
  error,
  onPageChange,
}: {
  title: string
  emptyTitle: string
  emptyBody: string
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  totalRecords: number
  page: number
  pageSize: number
  isLoading: boolean
  isRefreshing: boolean
  error: string | null
  onPageChange: (page: number) => void
}) {
  const lastPage = Math.max(1, Math.ceil(totalRecords / pageSize))

  return (
    <section className="space-y-3">
      <h2 className="micro-label">{title}</h2>
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={rowKey}
        isLoading={isLoading}
        isRefreshing={isRefreshing}
        error={error}
        emptyTitle={emptyTitle}
        emptyBody={emptyBody}
        skeletonRows={6}
      />
      {totalRecords > pageSize && (
        <div className="flex items-center justify-end gap-3 text-xs text-ink-muted">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1 || isLoading || isRefreshing}
            onClick={() => onPageChange(page - 1)}
          >
            ‹
          </Button>
          <span className="num">
            {page} / {lastPage}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= lastPage || isLoading || isRefreshing}
            onClick={() => onPageChange(page + 1)}
          >
            ›
          </Button>
        </div>
      )}
    </section>
  )
}

/** Pagination for the orders tab, whose cards do not fit the table shell above. */
function SimplePagination({
  totalRecords,
  page,
  pageSize,
  isLoading,
  error,
  onPageChange,
}: {
  totalRecords: number
  page: number
  pageSize: number
  isLoading: boolean
  error: string | null
  onPageChange: (page: number) => void
}) {
  const lastPage = useMemo(() => Math.max(1, Math.ceil(totalRecords / pageSize)), [totalRecords, pageSize])

  if (error && totalRecords === 0) return null
  if (totalRecords <= pageSize) return null

  return (
    <div className="flex items-center justify-end gap-3 text-xs text-ink-muted">
      <Button variant="outline" size="sm" disabled={page <= 1 || isLoading} onClick={() => onPageChange(page - 1)}>
        ‹
      </Button>
      <span className="num">
        {page} / {lastPage}
      </span>
      <Button
        variant="outline"
        size="sm"
        disabled={page >= lastPage || isLoading}
        onClick={() => onPageChange(page + 1)}
      >
        ›
      </Button>
    </div>
  )
}
