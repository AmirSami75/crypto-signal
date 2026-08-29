import { useCallback, useState } from 'react'
import { fa } from '../i18n/fa'
import { StatusDot } from '../components/ui/Badge'
import { Button, buttonClasses } from '../components/ui/Button'
import { Card, Eyebrow } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { BarChart } from '../components/ui/Charts'
import { Alert } from '../components/ui/Alert'
import { api } from '../lib/api'
import type { MlSupportedMarket } from '../lib/apiTypes'
import { useResource } from '../lib/useResource'
import { dateTimeText, percentText } from '../lib/tradingFormat'

/**
 * The M Engine screen: one place to read what the model layer is doing.
 *
 * It answers three operator questions at a glance:
 * 1. Which model is live, and how old is it? (MlModelInfo)
 * 2. What markets does the engine cover, and which symbol/version is served? (MlCapabilities)
 * 3. Does the calibration look sane — i.e. does confidence track win rate? (MlModelInfo.confidenceReach)
 *
 * The retraining driver (`self_learning_loop.py`) runs on a weekly cron and hot-reloads in place, so
 * this page has no "start training" button: promoting a candidate is deliberately an autonomous,
 * gate-checked process, not a manual trigger that could be fired at the market. What the page *does*
 * show is the result of that gate — the live version string and its trained timestamp — so an operator
 * can tell at a glance whether the model on screen matches the one that was trained.
 */

const POLL_INTERVAL = 60_000

export function MlEnginePage() {
  const [showAllMarkets, setShowAllMarkets] = useState(false)

  const capabilitiesFetcher = useCallback(
    (signal?: AbortSignal) => api.ml.capabilities(signal),
    [],
  )
  const {
    data: capabilities,
    error: capsError,
    isLoading: capsLoading,
    refetch: refetchCapabilities,
  } = useResource(capabilitiesFetcher)

  const modelFetcher = useCallback(
    (signal?: AbortSignal) => api.ml.model({}, signal),
    [],
  )
  const {
    data: model,
    error: modelError,
    isLoading: modelLoading,
    refetch: refetchModel,
  } = useResource(modelFetcher)

  const isReady = capabilities?.modelReady ?? false
  const markets = capabilities?.supportedMarkets ?? []
  const displayedMarkets = showAllMarkets ? markets : markets.slice(0, Math.min(markets.length, 6))

  const confidenceReach = model?.confidenceReach ?? []
  const bucketLabels = confidenceReach.map((b) => `${Math.round(b.threshold * 100)}%+`)
  const bucketValues = confidenceReach.map((b) => b.share * 100)

  const versionShort = (model?.modelVersion ?? '').slice(0, 12)

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-[1.375rem] font-semibold">{fa.nav.ml}</h1>
        {capsLoading || modelLoading ? (
          <Spinner size="sm" />
        ) : (
          <span
            className="flex items-center gap-1.5 text-sm"
          >
            <StatusDot tone={isReady ? 'success' : 'danger'} />
            <span>{isReady ? fa.mlEngine.stateReady : fa.mlEngine.stateNotReady}</span>
          </span>
        )}
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            refetchCapabilities()
            refetchModel()
          }}
          className="ms-auto"
        >
          {fa.common.refresh}
        </Button>
      </header>

      {capsError && <Alert tone="error">{fa.mlEngine.capsLoadFailed}</Alert>}
      {modelError && <Alert tone="error">{fa.mlEngine.modelLoadFailed}</Alert>}

      {/* Capabilities summary */}
      <section
        aria-label={fa.mlEngine.capabilitiesLabel}
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        <StatValue
          label={fa.mlEngine.serviceLabel}
          value={capabilities?.service ?? '—'}
          caption={capabilities ? `${fa.mlEngine.versionLabel} ${capabilities.serviceVersion}` : undefined}
        />
        <StatValue
          label={fa.mlEngine.protocolLabel}
          value={capabilities?.protocolVersion ?? '—'}
          caption={fa.mlEngine.minCandlesLabel}
        />
        <StatValue
          label={fa.mlEngine.marketsLabel}
          value={markets.length > 0 ? markets.length.toString() : '—'}
          caption={fa.mlEngine.marketsCaption}
        />
        <StatValue
          label={fa.mlEngine.wildcardLabel}
          value={capabilities?.wildcardModelReady ? fa.common.active : fa.common.inactive}
          tone={capabilities?.wildcardModelReady ? 'success' : 'neutral'}
        />
      </section>

      {/* Active model card */}
      <Card as="section" className="p-6 sm:p-7">
        <Eyebrow>{fa.mlEngine.activeModelLabel}</Eyebrow>
        {modelLoading ? (
          <div className="mt-4">
            <Spinner />
          </div>
        ) : model ? (
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatValue
              label={fa.mlEngine.modelVersionLabel}
              value={versionShort || '—'}
              caption={fa.mlEngine.modelVersionNote}
            />
            <StatValue
              label={fa.mlEngine.trainedAtLabel}
              value={model.trainedAt ? dateTimeText(model.trainedAt) : '—'}
              caption={fa.mlEngine.trainedAtNote}
            />
            <StatValue
              label={fa.mlEngine.featureCountLabel}
              value={model.featureCount.toString()}
              caption={fa.mlEngine.featureCountNote}
            />
            <StatValue
              label={fa.mlEngine.confidenceCeilingLabel}
              value={percentText(model.confidenceCeiling * 100, 1)}
              caption={fa.mlEngine.confidenceCeilingNote}
            />
            <StatValue
              label={fa.mlEngine.holdingPeriodsLabel}
              value={model.defaultMaxHoldingPeriods.toString()}
              caption={fa.mlEngine.holdingPeriodsNote}
            />
            <StatValue
              label={fa.mlEngine.labelSchemeLabel}
              value={model.labelScheme}
              caption={fa.mlEngine.calibrationMethodLabel}
            />
          </div>
        ) : (
          <p className="mt-4 text-sm text-ink-muted">{fa.mlEngine.modelNotReady}</p>
        )}
      </Card>

      {/* Confidence calibration: does confidence track win rate? */}
      {model && confidenceReach.length > 0 && (
        <Card as="section" className="p-6 sm:p-7">
          <Eyebrow>{fa.mlEngine.calibrationLabel}</Eyebrow>
          <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
            {fa.mlEngine.calibrationNote}
          </p>
          <div className="mt-5">
            <BarChart
              values={bucketValues}
              labels={bucketLabels}
              ariaLabel={fa.mlEngine.calibrationLabel}
            />
          </div>
        </Card>
      )}

      {/* Supported markets */}
      <Card as="section" className="p-6 sm:p-7">
        <div className="flex items-baseline justify-between gap-3">
          <Eyebrow>{fa.mlEngine.marketsLabel}</Eyebrow>
          {markets.length > 6 && (
            <button
              type="button"
              onClick={() => setShowAllMarkets(!showAllMarkets)}
              className="text-xs font-medium text-accent underline-offset-2 hover:underline"
            >
              {showAllMarkets ? fa.mlEngine.hideMarkets : fa.mlEngine.showAllMarkets}
            </button>
          )}
        </div>
        <div className="mt-4 -mx-1 -mx-5 sm:mx-0 sm:overflow-x-auto">
          <table className="w-full min-w-[38rem] border-collapse text-sm sm:min-w-0">
            <thead>
              <tr>
                <th className="text-start font-semibold">{fa.mlEngine.colSymbol}</th>
                <th className="text-start font-semibold">{fa.mlEngine.colInterval}</th>
                <th className="text-start font-medium">{fa.mlEngine.colVersion}</th>
                <th className="text-start font-semibold">{fa.mlEngine.colWildcard}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {displayedMarkets.map((market) => (
                <MarketRow key={`${market.symbol}:${market.interval}:${market.modelVersion}`} market={market} />
              ))}
              {!showAllMarkets && markets.length > 6 && (
                <tr>
                  <td colSpan={4} className="py-2 text-center text-xs text-ink-faint">
                    +{markets.length - 6} {fa.mlEngine.moreMarkets}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

/** A market row: symbol, interval, served version, wildcard flag. */
function MarketRow({ market }: { market: MlSupportedMarket }) {
  const versionShort = (market.modelVersion ?? '').slice(0, 12)
  return (
    <tr>
      <td className="py-2.5 font-medium" dir="ltr">
        {market.symbol}
      </td>
      <td className="py-2.5 text-ink-muted" dir="ltr">
        {market.interval}
      </td>
      <td className="py-2.5 text-ink-faint" dir="ltr">
        {versionShort || '—'}
      </td>
      <td className="py-2.5">
        {market.isWildcard ? (
          <span className="flex items-center gap-1.5 text-xs">
            <StatusDot tone="accent" />
            <span>{fa.mlEngine.wildcardYes}</span>
          </span>
        ) : (
          <span className="text-ink-faint">{fa.common.no}</span>
        )}
      </td>
    </tr>
  )
}

/**
 * A labelled figure. `tone` colours the value, matching Badge's palette.
 */
function StatValue({
  label,
  value,
  caption,
  tone = 'neutral',
}: {
  label: string
  value: string
  caption?: string
  tone?: 'neutral' | 'success' | 'danger' | 'warn'
}) {
  const toneClass =
    tone === 'success'
      ? 'text-success'
      : tone === 'danger'
        ? 'text-danger'
        : tone === 'warn'
          ? 'text-warning'
          : 'text-ink'
  return (
    <div className="flex flex-col gap-1">
      <p className="micro-label">{label}</p>
      <span className={`num text-lg font-semibold ${toneClass}`}>{value}</span>
      {caption && <span className="text-xs text-ink-muted">{caption}</span>}
    </div>
  )
}
