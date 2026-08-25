import { useCallback, useEffect, useMemo, useState } from 'react'
import { Checkbox } from '../components/ui/Checkbox'
import { Field } from '../components/ui/Field'
import { Input } from '../components/ui/Input'
import { Select } from '../components/ui/Select'
import { Button } from '../components/ui/Button'
import { Alert } from '../components/ui/Alert'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { DirectionBadge, normalizeMode } from '../components/trading/TradingBadges'
import { fa } from '../i18n/fa'
import { api } from '../lib/api'
import type { Signal, SignalRequest, MarketVenueName } from '../lib/apiTypes'
import {
  priceText,
  shareText,
  ratioText,
  percentText,
  dateTimeText,
  countdownText,
  secondsUntil,
  digestText,
  countText,
} from '../lib/tradingFormat'
import { usePlatform } from '../lib/usePlatform'

const INTERVALS = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w']
const VENUES: MarketVenueName[] = ['BinanceTestnet', 'BinanceMainnet']

/**
 * Capability 2: one calibrated signal for one requested market.
 *
 * The candle window is fetched server-side; the browser never sends price data to the model.
 * The signal is evidence, not authorization — nothing here places an order.
 */
export function SignalPage() {
  const { data: platform } = usePlatform()
  const operatingMode = platform?.operatingMode ? normalizeMode(platform.operatingMode) : null

  const [symbol, setSymbol] = useState('BTCUSDT')
  const [interval, setInterval] = useState('1h')
  const [takeProfitPercent, setTakeProfitPercent] = useState('2')
  const [stopLossPercent, setStopLossPercent] = useState('1')
  const [allowShort, setAllowShort] = useState(false)
  const [venue, setVenue] = useState<MarketVenueName>('BinanceTestnet')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [maxHoldingPeriods, setMaxHoldingPeriods] = useState('')
  const [minimumConfidence, setMinimumConfidence] = useState('')

  const [signal, setSignal] = useState<Signal | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [validitySeconds, setValiditySeconds] = useState<number | null>(null)

  // Countdown tick
  useEffect(() => {
    if (validitySeconds === null || validitySeconds <= 0) return

    // window.* — the page keeps a state setter named `setInterval`, so the bare global would
    // resolve to it and the timer would never be registered.
    const timer = window.setInterval(() => {
      setValiditySeconds(prev => (prev && prev > 1 ? prev - 1 : null))
    }, 1000)

    return () => window.clearInterval(timer)
  }, [validitySeconds])

  const handleSubmit = useCallback(async () => {
    const tp = parseFloat(takeProfitPercent)
    const sl = parseFloat(stopLossPercent)

    if (!symbol.trim()) {
      setError('نماد را وارد کنید')
      return
    }
    if (isNaN(tp) || tp <= 0) {
      setError('درصد حد سود باید عددی مثبت باشد')
      return
    }
    if (isNaN(sl) || sl <= 0) {
      setError('درصد حد ضرر باید عددی مثبت باشد')
      return
    }

    setIsLoading(true)
    setError(null)
    setSignal(null)
    setValiditySeconds(null)

    const request: SignalRequest = {
      symbol: symbol.trim().toUpperCase(),
      interval,
      takeProfitPercent: tp,
      stopLossPercent: sl,
      allowShort,
      venue,
      maxHoldingPeriods: maxHoldingPeriods ? parseInt(maxHoldingPeriods, 10) : undefined,
      minimumConfidence: minimumConfidence ? parseFloat(minimumConfidence) : undefined,
    }

    try {
      const result = await api.signals.get(request)
      setSignal(result)

      if (result.validUntil) {
        const secs = secondsUntil(result.validUntil)
        if (secs && secs > 0) setValiditySeconds(secs)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'خطا در دریافت سیگنال')
    } finally {
      setIsLoading(false)
    }
  }, [symbol, interval, takeProfitPercent, stopLossPercent, allowShort, venue, maxHoldingPeriods, minimumConfidence])

  const rationaleText = useMemo(() => {
    if (!signal?.rationale.length) return null
    return signal.rationale.map(r => `• ${r}`).join('\n')
  }, [signal])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <h1 className="text-xl font-semibold text-ink">{fa.signal.title}</h1>
        <p className="text-sm text-ink-soft">{fa.signal.subtitle}</p>
      </div>

      {/* Evidence notice - prominent on every signal screen */}
      <Alert tone="info" title="">
        {fa.trading.evidenceNote}
      </Alert>

      {/* Operating mode badge */}
      {operatingMode && (
        <div className="flex items-center gap-2 text-sm text-ink-soft">
          <span>{fa.trading.modeLabel}:</span>
          <Badge tone="accent">{operatingMode}</Badge>
        </div>
      )}

      {/* Form */}
      <Card className="space-y-4">
        <h2 className="font-medium text-ink">{fa.signal.formLabel}</h2>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label={fa.trading.symbol} hint={fa.signal.symbolHint} required>
            {ids => (
              <Input
                {...ids}
                value={symbol}
                onChange={e => setSymbol(e.target.value.toUpperCase())}
                placeholder="BTCUSDT"
                isInvalid={!!error && !symbol.trim()}
              />
            )}
          </Field>

          <Field label={fa.trading.interval} hint={fa.signal.intervalHint} required>
            {ids => (
              <Select {...ids} value={interval} onChange={e => setInterval(e.target.value)}>
                {INTERVALS.map(i => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </Select>
            )}
          </Field>

          <Field label={fa.trading.takeProfitPercent} hint={fa.signal.takeProfitHint} required>
            {ids => (
              <Input
                {...ids}
                type="number"
                step="0.1"
                min="0"
                value={takeProfitPercent}
                onChange={e => setTakeProfitPercent(e.target.value)}
                placeholder="2"
              />
            )}
          </Field>

          <Field label={fa.trading.stopLossPercent} hint={fa.signal.stopLossHint} required>
            {ids => (
              <Input
                {...ids}
                type="number"
                step="0.1"
                min="0"
                value={stopLossPercent}
                onChange={e => setStopLossPercent(e.target.value)}
                placeholder="1"
              />
            )}
          </Field>
        </div>

        <div className="flex flex-wrap items-center gap-6 pt-2">
          <Checkbox checked={allowShort} onChange={setAllowShort} label={fa.trading.allowShort} />
        </div>

        {/* Venue selector */}
        <Field label={fa.trading.venueLabel}>
          {ids => (
            <Select {...ids} value={venue} onChange={e => setVenue(e.target.value as MarketVenueName)}>
              {VENUES.map(v => (
                <option key={v} value={v}>
                  {fa.trading.venue[v] ?? v}
                </option>
              ))}
            </Select>
          )}
        </Field>

        {/* Advanced toggle */}
        <button
          type="button"
          onClick={() => setShowAdvanced(s => !s)}
          className="text-sm text-accent hover:underline"
        >
          {fa.signal.advanced} {showAdvanced ? '▲' : '▼'}
        </button>

        {showAdvanced && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={fa.trading.minimumConfidence} hint={fa.signal.minimumConfidenceHint}>
              {ids => (
                <Input
                  {...ids}
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={minimumConfidence}
                  onChange={e => setMinimumConfidence(e.target.value)}
                  placeholder="0.5"
                />
              )}
            </Field>

            <Field label={fa.bots.maxHoldingPeriods} hint={fa.signal.maxHoldingHint}>
              {ids => (
                <Input
                  {...ids}
                  type="number"
                  min="1"
                  value={maxHoldingPeriods}
                  onChange={e => setMaxHoldingPeriods(e.target.value)}
                  placeholder="6"
                />
              )}
            </Field>
          </div>
        )}

        <p className="text-xs text-ink-faint">{fa.signal.candleSourceNote}</p>

        {error && (
          <Alert tone="error" title="">
            {error}
          </Alert>
        )}

        <div className="pt-2">
          <Button onClick={handleSubmit} isLoading={isLoading} disabled={isLoading}>
            {isLoading ? fa.signal.submitting : fa.signal.submit}
          </Button>
        </div>
      </Card>

      {/* Result */}
      {signal && (
        <Card className="space-y-6">
          <h2 className="font-medium text-ink">{fa.signal.resultLabel}</h2>

          {/* Direction */}
          <div className="flex items-center gap-4">
            <span className="text-ink-soft">{fa.trading.directionLabel}:</span>
            <DirectionBadge direction={signal.direction} />
            {signal.usedWildcardModel && (
              <span className="text-xs text-ink-faint" title={fa.trading.pooledModelNote}>
                ({fa.trading.pooledModel})
              </span>
            )}
          </div>

          {/* Flat case */}
          {signal.direction === 'Flat' && (
            <Alert tone="info" title={fa.signal.flatTitle}>
              {fa.signal.flatBody}
            </Alert>
          )}

          {/* Levels card - only when direction is Long/Short */}
          {signal.direction !== 'Flat' && signal.levels && (
            <div className="rounded-xl border border-line bg-surface-muted p-4 space-y-4">
              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <p className="text-xs text-ink-faint">{fa.trading.entryPrice}</p>
                  <p className="text-lg font-semibold text-ink num">{priceText(signal.levels.entryPrice)}</p>
                </div>
                <div>
                  <p className="text-xs text-ink-faint">{fa.trading.takeProfitPrice}</p>
                  <p className="text-lg font-semibold text-success num">{priceText(signal.levels.takeProfitPrice)}</p>
                </div>
                <div>
                  <p className="text-xs text-ink-faint">{fa.trading.stopLossPrice}</p>
                  <p className="text-lg font-semibold text-danger num">{priceText(signal.levels.stopLossPrice)}</p>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-4 text-sm">
                <div>
                  <span className="text-ink-faint">{fa.trading.confidence}: </span>
                  <span className="num font-medium">{shareText(signal.confidence)}</span>
                </div>
                <div>
                  <span className="text-ink-faint">{fa.trading.riskReward}: </span>
                  <span className="num font-medium">{ratioText(signal.levels.riskRewardRatio)}</span>
                </div>
                <div>
                  <span className="text-ink-faint">{fa.trading.atr}: </span>
                  <span className="num font-medium">{priceText(signal.levels.atr)}</span>
                </div>
                <div>
                  <span className="text-ink-faint">{fa.trading.expectedValue}: </span>
                  <span className="num font-medium">{signal.expectedValue.toFixed(4)}</span>
                </div>
              </div>

              {/* Barrier distances in ATR */}
              <div className="text-xs text-ink-faint">
                {fa.signal.barrierAtr}: TP {signal.levels.takeProfitAtr.toFixed(2)} ATR / SL{' '}
                {signal.levels.stopLossAtr.toFixed(2)} ATR
              </div>
            </div>
          )}

          {/* Extrapolated warning */}
          {signal.barrierExtrapolated && (
            <Alert tone="warn" title={fa.trading.extrapolated}>
              {fa.trading.extrapolatedNote}
            </Alert>
          )}

          {/* Confidence breakdown */}
          <div className="space-y-2">
            <p className="text-sm font-medium text-ink">{fa.signal.probabilityLabel}</p>
            <div className="grid gap-2 sm:grid-cols-3 text-sm">
              <div className="flex justify-between rounded-lg bg-surface-muted px-3 py-2">
                <span className="text-ink-soft">{fa.signal.probTakeProfit}</span>
                <span className="num font-medium text-success">{shareText(signal.probabilities.takeProfitFirst)}</span>
              </div>
              <div className="flex justify-between rounded-lg bg-surface-muted px-3 py-2">
                <span className="text-ink-soft">{fa.signal.probStopLoss}</span>
                <span className="num font-medium text-danger">{shareText(signal.probabilities.stopLossFirst)}</span>
              </div>
              <div className="flex justify-between rounded-lg bg-surface-muted px-3 py-2">
                <span className="text-ink-soft">{fa.signal.probTimeout}</span>
                <span className="num font-medium">{shareText(signal.probabilities.timeout)}</span>
              </div>
            </div>
          </div>

          {/* Long/Short confidence breakdown */}
          <div className="grid gap-2 sm:grid-cols-2 text-sm">
            <div className="flex justify-between rounded-lg bg-surface-muted px-3 py-2">
              <span className="text-ink-soft">{fa.signal.longSide}</span>
              <span className="num font-medium">{shareText(signal.longConfidence)}</span>
            </div>
            <div className="flex justify-between rounded-lg bg-surface-muted px-3 py-2">
              <span className="text-ink-soft">{fa.signal.shortSide}</span>
              <span className="num font-medium">{shareText(signal.shortConfidence)}</span>
            </div>
          </div>

          {/* Validity countdown */}
          {signal.validUntil && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-ink-faint">{fa.trading.validUntil}:</span>
              {validitySeconds !== null && validitySeconds > 0 ? (
                <span className="num font-medium text-accent">{countdownText(validitySeconds)}</span>
              ) : (
                <span className="text-danger">{fa.signal.validityExpired}</span>
              )}
            </div>
          )}

          {/* Meta */}
          <div className="grid gap-2 text-xs text-ink-faint sm:grid-cols-2">
            <div>
              {fa.trading.candleTime}: <span className="num">{dateTimeText(signal.candleOpenTime)}</span>
            </div>
            <div>
              {fa.trading.modelVersion}: <span className="num latin">{signal.modelVersion}</span>
            </div>
            <div>
              {fa.signal.candleCount}: <span className="num">{countText(signal.candleCount)}</span>
            </div>
            <div>
              {fa.signal.processing}: <span className="num">{signal.processingMilliseconds.toFixed(0)}</span>{' '}
              {fa.signal.milliseconds}
            </div>
            <div className="sm:col-span-2">
              {fa.signal.digest}: <span className="num latin">{digestText(signal.inputDigestSha256)}</span>
            </div>
          </div>

          {/* Rationale */}
          {rationaleText && (
            <div className="text-sm text-ink-soft">
              <p className="font-medium text-ink">{fa.signal.rationale}:</p>
              <pre className="mt-1 whitespace-pre-wrap text-xs">{rationaleText}</pre>
            </div>
          )}

          {/* Engine warning */}
          {signal.warning && (
            <Alert tone="warn" title={fa.signal.engineWarning}>
              {signal.warning}
            </Alert>
          )}
        </Card>
      )}
    </div>
  )
}
