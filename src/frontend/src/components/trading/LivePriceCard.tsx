import { useCallback, useState } from 'react'
import { CandleChart } from '../ui/Charts'
import { fa } from '../../i18n/fa'
import { api } from '../../lib/api'
import type { BotDetail, ChartCandle } from '../../lib/apiTypes'
import { useInterval } from '../../lib/useInterval'

const INTERVALS = ['15m', '1h', '4h'] as const
type ChartInterval = (typeof INTERVALS)[number]

/**
 * Live price panel for one bot's market: candles from the venue, routed through our API because
 * the venue sends no CORS headers. Refreshes on its own cadence — price is the thing operators
 * glance at most, so it polls faster than the rest of the page and carries its own interval
 * switch instead of coupling to the bot's evaluation interval.
 */
export function LivePriceCard({ bot }: { bot: BotDetail }) {
  const [interval, setIntervalState] = useState<ChartInterval>('15m')

  return (
    <section className="space-y-3 rounded-xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="micro-label">{fa.monitor.priceLabel}</h2>
        <div className="flex gap-1" role="tablist" aria-label={fa.monitor.intervalLabel}>
          {INTERVALS.map(option => (
            <button
              key={option}
              role="tab"
              aria-selected={option === interval}
              onClick={() => setIntervalState(option)}
              className={`num rounded px-2 py-0.5 text-xs transition-colors ${
                option === interval ? 'bg-accent/15 text-accent-ink' : 'text-ink-muted hover:bg-surface-hover'
              }`}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      <PriceChartBody venue={bot.venue} symbol={bot.symbol} interval={interval} />
    </section>
  )
}

function PriceChartBody({ venue, symbol, interval }: { venue: string; symbol: string; interval: string }) {
  const [candles, setCandles] = useState<ChartCandle[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(() => {
    api.charts.candles(venue, symbol, interval, 96)
      .then(data => {
        setCandles(data)
        setError(null)
      })
      .catch(cause => setError(cause instanceof Error ? cause.message : String(cause)))
  }, [venue, symbol, interval])

  useInterval(refetch, 30_000)

  if (error && !candles) return <p className="text-sm text-danger">{error}</p>
  if (!candles) return <p className="text-sm text-ink-faint">{fa.common.loading}</p>

  const last = candles[candles.length - 1]
  const first = candles[0]
  const rising = last.close >= first.open

  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-3">
        <span className={`num text-xl font-semibold ${rising ? 'text-success' : 'text-danger'}`} dir="ltr">
          {last.close.toLocaleString('en-US', { maximumFractionDigits: 2 })}
        </span>
        <span className="num text-xs text-ink-faint" dir="ltr">
          {symbol} · {interval}
        </span>
      </div>
      <CandleChart candles={candles} ariaLabel={`${symbol} ${interval}`} height={130} />
    </div>
  )
}
