import { useCallback, useState } from 'react'
import { Alert } from '../ui/Alert'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { EmptyState } from '../ui/EmptyState'
import { Skeleton } from '../ui/Skeleton'
import { StatCard } from '../ui/StatCard'
import { fa } from '../../i18n/fa'
import { api } from '../../lib/api'
import type { BotTearsheet } from '../../lib/apiTypes'
import { useResource } from '../../lib/useResource'
import { countText, dateTimeText, ratioText, shareText } from '../../lib/tradingFormat'

/**
 * The performance tearsheet for one bot — `GET /api/v1/bot/{botId}/tearsheet`.
 *
 * Two facts shape everything on this panel, and both come from the payload rather than from taste:
 *
 * 1. **Every metric is nullable.** `null` means the figure is undefined, never zero — no trades, no
 *    losing trade to divide by, a zero-variance series. So every value goes through the `tradingFormat`
 *    helpers (which already collapse `null`, `NaN` and `Infinity` to an em dash) and a null is called
 *    out with a title rather than rendered as `0`. A win rate of `0%` and a win rate of "nothing to
 *    measure" are different claims.
 * 2. **`fillsIncluded` says what the numbers *are*.** When it is false the trade series is the entry
 *    decisions' expected value, not realised P&L, and the same win rate means something different.
 *    That is stated on the panel in words, because the numbers alone do not reveal it.
 *
 * The period selector is a segmented control rather than a `<select>`: three fixed options with a
 * current one is exactly the shape of a tab strip, and it keeps the whole control one tap wide on a
 * phone.
 */

const PERIODS = [7, 30, 90] as const
type Period = (typeof PERIODS)[number]

/** The em dash a null metric renders as, with the reason attached on hover. */
function Absent() {
  return (
    <span className="text-ink-faint" title={fa.tearsheet.undefinedMetric}>
      —
    </span>
  )
}

export function TearsheetPanel({ botId }: { botId: string }) {
  const [days, setDays] = useState<Period>(30)

  const fetcher = useCallback(
    (signal?: AbortSignal) => api.bots.tearsheet(botId, days, signal),
    [botId, days],
  )
  const { data, error, isLoading, isRefreshing, refetch } = useResource(fetcher)

  return (
    <div className="space-y-5">
      <PeriodSelector days={days} onChange={setDays} />

      {isLoading && !data && <TearsheetSkeleton />}

      {error && !data && (
        <div className="space-y-3">
          <Alert tone="error">{error}</Alert>
          <Button variant="outline" size="sm" onClick={refetch}>
            {fa.common.retry}
          </Button>
        </div>
      )}

      {data && data.decisions === 0 && (
        <EmptyState
          title={fa.tearsheet.emptyTitle}
          body={fa.tearsheet.emptyBody}
          action={
            <Button variant="outline" size="sm" onClick={refetch}>
              {fa.common.retry}
            </Button>
          }
        />
      )}

      {data && data.decisions > 0 && (
        <div className={isRefreshing ? 'space-y-5 opacity-60 transition-opacity' : 'space-y-5'}>
          {/* A failed refetch annotates the figures already on screen rather than blanking them. */}
          {error && <Alert tone="error">{error}</Alert>}

          <p className="text-xs text-ink-faint">
            {fa.tearsheet.periodRange}:{' '}
            <span className="num">{dateTimeText(data.period.from)}</span> {fa.tearsheet.periodRangeTo}{' '}
            <span className="num">{dateTimeText(data.period.to)}</span>
          </p>

          <FillsNotice fillsIncluded={data.fillsIncluded} />

          <MetricGrid tearsheet={data} />

          <ReasonBreakdown reasonBreakdown={data.reasonBreakdown} />

          <ConfidenceHistogram bins={data.confidenceHistogram} />
        </div>
      )}
    </div>
  )
}

// ─── Period selector ──────────────────────────────────────────────────────────────────────────────

function PeriodSelector({ days, onChange }: { days: Period; onChange: (days: Period) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="micro-label shrink-0">{fa.tearsheet.periodLabel}</span>
      <div
        role="group"
        aria-label={fa.tearsheet.periodLabel}
        className="flex flex-wrap gap-1 rounded-xl border border-line bg-surface p-1"
      >
        {PERIODS.map(period => (
          <button
            key={period}
            type="button"
            aria-pressed={days === period}
            onClick={() => onChange(period)}
            className={[
              'rounded-lg px-3.5 py-2 text-sm transition-colors',
              days === period ? 'bg-surface-muted font-medium text-ink' : 'text-ink-muted hover:text-ink',
            ].join(' ')}
          >
            <span className="num">{fa.tearsheet.periodOption(period)}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

// ─── The fills notice ─────────────────────────────────────────────────────────────────────────────

/**
 * The one line that changes how every figure above it should be read. It is an `Alert`, not a badge,
 * because it is a qualification on the whole panel rather than a property of one metric.
 */
function FillsNotice({ fillsIncluded }: { fillsIncluded: boolean }) {
  return (
    <Alert tone={fillsIncluded ? 'info' : 'warn'}>
      {fillsIncluded ? fa.tearsheet.fillsIncludedNote : fa.tearsheet.decisionsOnlyNotice}
    </Alert>
  )
}

// ─── Metric cards ─────────────────────────────────────────────────────────────────────────────────

function MetricGrid({ tearsheet: t }: { tearsheet: BotTearsheet }) {
  return (
    <section className="space-y-3">
      <h3 className="micro-label">{fa.tearsheet.metricsLabel}</h3>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={fa.tearsheet.decisions}
          value={<span className="num">{countText(t.decisions)}</span>}
          caption={fa.tearsheet.decisionsCaption}
        />
        <StatCard
          label={fa.tearsheet.entries}
          value={<span className="num">{countText(t.entries)}</span>}
          caption={fa.tearsheet.entriesCaption}
        />
        <StatCard
          label={fa.tearsheet.winRate}
          value={t.winRate === null ? <Absent /> : <span className="num">{shareText(t.winRate)}</span>}
          caption={fa.tearsheet.winRateCaption}
        />
        <StatCard
          label={fa.tearsheet.expectancyAtr}
          value={t.expectancyAtr === null ? <Absent /> : <span className="num">{ratioText(t.expectancyAtr, 3)}</span>}
          caption={fa.tearsheet.expectancyAtrCaption}
        />
        <StatCard
          label={fa.tearsheet.profitFactor}
          value={t.profitFactor === null ? <Absent /> : <span className="num">{ratioText(t.profitFactor, 2)}</span>}
          caption={fa.tearsheet.profitFactorCaption}
        />
        <StatCard
          label={fa.tearsheet.sharpe}
          value={t.sharpe === null ? <Absent /> : <span className="num">{ratioText(t.sharpe, 2)}</span>}
          caption={fa.tearsheet.sharpeCaption}
        />
        <StatCard
          label={fa.tearsheet.maxDrawdown}
          value={t.maxDrawdown === null ? <Absent /> : <span className="num">{ratioText(t.maxDrawdown, 2)}</span>}
          caption={fa.tearsheet.maxDrawdownCaption}
        />
        <StatCard
          label={fa.tearsheet.romad}
          value={t.romad === null ? <Absent /> : <span className="num">{ratioText(t.romad, 2)}</span>}
          caption={fa.tearsheet.romadCaption}
        />
      </div>
    </section>
  )
}

// ─── Reason breakdown ─────────────────────────────────────────────────────────────────────────────

/**
 * Why the bot acted as it did, one horizontal bar per `reason_code`.
 *
 * Bars rather than a pie: the reading is "which reason dominates", and a length against a shared
 * baseline answers that at a glance. They are laid out with logical properties, so under `dir="rtl"`
 * they grow from the right, which is where a reader's eye starts. Sorted by count, so the reader does
 * not have to sort.
 */
function ReasonBreakdown({ reasonBreakdown }: { reasonBreakdown: Record<string, number> }) {
  const entries = Object.entries(reasonBreakdown).sort((a, b) => b[1] - a[1])
  const max = entries.length > 0 ? Math.max(1, ...entries.map(([, count]) => count)) : 1

  return (
    <section className="space-y-3">
      <h3 className="micro-label">{fa.tearsheet.breakdownLabel}</h3>
      <Card className="p-5">
        {entries.length === 0 ? (
          <p className="text-sm text-ink-faint">{fa.tearsheet.breakdownEmpty}</p>
        ) : (
          <ul className="space-y-4">
            {entries.map(([reason, count]) => (
              <li key={reason} className="space-y-1.5">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm text-ink">{fa.tearsheet.reasonCode[reason] ?? reason}</span>
                  <span className="num shrink-0 text-xs text-ink-muted">{countText(count)}</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-surface-muted">
                  <div
                    className="h-full rounded-full bg-accent"
                    style={{ width: `${Math.max(2, (count / max) * 100)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </section>
  )
}

// ─── Confidence histogram ─────────────────────────────────────────────────────────────────────────

/**
 * Ten bins over the decisions' confidence, `[0, 0.1) … [0.9, 1.0]`.
 *
 * Drawn as a dependency-free inline SVG for the same reason `ui/Charts.tsx` is: a charting library
 * would bring its own layout and direction opinions to a themed, RTL page. The `<svg>` sets
 * `direction: ltr` on itself, so the low-confidence bin stays on the physical left where an axis
 * belongs, regardless of the document's script direction.
 */
function ConfidenceHistogram({ bins }: { bins: number[] }) {
  const WIDTH = 300
  const HEIGHT = 96
  const PAD = 4
  const GAP = 3

  const hasBins = bins.length > 0
  const max = hasBins ? Math.max(1, ...bins) : 1
  const slotWidth = (WIDTH - PAD * 2) / Math.max(1, bins.length)
  const barWidth = Math.max(1, slotWidth - GAP)

  return (
    <section className="space-y-3">
      <h3 className="micro-label">{fa.tearsheet.histogramLabel}</h3>
      <Card className="space-y-3 p-5">
        {!hasBins ? (
          <p className="text-sm text-ink-faint">{fa.tearsheet.histogramEmpty}</p>
        ) : (
          <>
            <svg
              viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
              preserveAspectRatio="none"
              className="w-full"
              style={{ height: HEIGHT, direction: 'ltr' }}
              role="img"
              aria-label={fa.tearsheet.histogramLabel}
            >
              {bins.map((count, index) => {
                const height = (count / max) * (HEIGHT - PAD * 2)
                return (
                  <rect
                    key={index}
                    x={(PAD + index * slotWidth + GAP / 2).toFixed(2)}
                    y={(HEIGHT - PAD - height).toFixed(2)}
                    width={barWidth.toFixed(2)}
                    height={height.toFixed(2)}
                    rx="2"
                    fill="var(--brand)"
                    fillOpacity="0.55"
                  >
                    <title>{`${index * 10}–${index * 10 + 10}%: ${count}`}</title>
                  </rect>
                )
              })}
              <line
                x1={PAD}
                y1={HEIGHT - PAD}
                x2={WIDTH - PAD}
                y2={HEIGHT - PAD}
                stroke="var(--line)"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
              />
            </svg>

            <div className="flex gap-1" dir="ltr" aria-hidden="true">
              {bins.map((_, index) => (
                <span key={index} className="num flex-1 text-center text-[0.625rem] text-ink-faint">
                  {index * 10}
                </span>
              ))}
            </div>

            <p className="text-xs text-ink-faint">{fa.tearsheet.histogramNote}</p>
          </>
        )}
      </Card>
    </section>
  )
}

// ─── Loading ──────────────────────────────────────────────────────────────────────────────────────

/** Sized to the loaded layout — a skeleton that does not match what replaces it causes the jump it exists to prevent. */
function TearsheetSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-4 w-48" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 8 }, (_, index) => (
          <Skeleton key={index} className="h-28 w-full rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-40 w-full rounded-xl" />
      <Skeleton className="h-40 w-full rounded-xl" />
    </div>
  )
}
