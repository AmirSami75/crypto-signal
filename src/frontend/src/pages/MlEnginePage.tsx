import { useCallback, useState } from 'react'
import { fa } from '../i18n/fa'
import { StatusDot } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, Eyebrow } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { BarChart } from '../components/ui/Charts'
import { Alert } from '../components/ui/Alert'
import { api } from '../lib/api'
import type { MlMarketTrainingStatus, MlModelInfo, MlSupportedMarket } from '../lib/apiTypes'
import { useResource } from '../lib/useResource'
import { useInterval } from '../lib/useInterval'
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

/** Confidence ceiling below which the model's discriminative power is suspect. */
const CEILING_WARN = 0.6

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

  const trainingFetcher = useCallback(
    (signal?: AbortSignal) => api.ml.trainingStatus(signal),
    [],
  )
  const { data: training, refetch: refetchTraining } = useResource(trainingFetcher)

  // Self-refresh on an interval — the engine hot-reloads, so a promoted model appears here without
  // a navigation. Manual refresh is still wired for the "I clicked deploy" case.
  const handleRefresh = useCallback(() => {
    refetchCapabilities()
    refetchModel()
    refetchTraining()
  }, [refetchCapabilities, refetchModel, refetchTraining])

  useInterval(handleRefresh, POLL_INTERVAL, !capsLoading && !modelLoading && capabilities !== null)

  const isReady = capabilities?.modelReady ?? false
  const markets = capabilities?.supportedMarkets ?? []
  const hasMarkets = markets.length > 0
  const displayedMarkets = showAllMarkets ? markets : markets.slice(0, 6)

  const confidenceReach = model?.confidenceReach ?? []
  const bucketLabels = confidenceReach.map((b) => `${Math.round(b.threshold * 100)}%+`)
  const bucketValues = confidenceReach.map((b) => b.share * 100)

  const versionShort = (model?.modelVersion ?? '').slice(0, 12)
  const trainedAt = model?.trainedAt ? dateTimeText(model.trainedAt) : null
  const ceilingLow = model && model.confidenceCeiling < CEILING_WARN

  const headerTone: 'success' | 'danger' | 'warn' = ceilingLow ? 'warn' : isReady ? 'success' : 'danger'
  const headerLabel = ceilingLow
    ? fa.mlEngine.stateLowCeiling
    : isReady
      ? fa.mlEngine.stateReady
      : fa.mlEngine.stateNotReady

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-[1.375rem] font-semibold">{fa.nav.ml}</h1>
        {capsLoading || modelLoading ? (
          <Spinner size="sm" />
        ) : (
          <span className="flex items-center gap-1.5 text-sm">
            <StatusDot tone={headerTone} />
            <span>{headerLabel}</span>
          </span>
        )}
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          className="ms-auto"
        >
          {fa.common.refresh}
        </Button>
      </header>

      {(capsError || modelError) && (
        <div className="space-y-2">
          {capsError && <Alert tone="error">{fa.mlEngine.capsLoadFailed}</Alert>}
          {modelError && <Alert tone="error">{fa.mlEngine.modelLoadFailed}</Alert>}
        </div>
      )}

      {/* Capabilities summary — skeleton-shaped cards while loading, so the grid does not jump */ }
      <section aria-label={fa.mlEngine.capabilitiesLabel} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatValue
          label={fa.mlEngine.serviceLabel}
          value={capabilities ? capabilities.service : <LoadingSkeleton width="w-32" />}
          caption={capabilities ? `${fa.mlEngine.versionLabel} ${capabilities.serviceVersion}` : undefined}
        />
        <StatValue
          label={fa.mlEngine.protocolLabel}
          value={capabilities ? capabilities.protocolVersion : <LoadingSkeleton width="w-16" />}
          caption={fa.mlEngine.minCandlesLabel}
        />
        <StatValue
          label={fa.mlEngine.marketsLabel}
          value={capsLoading ? <LoadingSkeleton width="w-8" /> : (hasMarkets ? markets.length.toString() : '—')}
          caption={fa.mlEngine.marketsCaption}
        />
        {capabilities && (
          <StatValue
            label={fa.mlEngine.wildcardLabel}
            value={capabilities.wildcardModelReady ? fa.common.active : fa.common.inactive}
            tone={capabilities.wildcardModelReady ? 'success' : 'neutral'}
          />
        )}
      </section>

      {/* Active model card */ }
      <Card as="section" className="p-6 sm:p-7">
        <div className="flex items-baseline justify-between gap-3">
          <Eyebrow>{fa.mlEngine.activeModelLabel}</Eyebrow>
          {trainedAt && (
            <span className="text-xs text-ink-faint">{`${fa.mlEngine.lastRefreshLabel} ${trainedAt}`}</span>
          )}
        </div>

        {modelLoading ? (
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <StatValue key={i} label={fa.mlEngine.modelLoadingLabel} value={<LoadingSkeleton width="w-24" />} />
            ))}
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
              value={trainedAt ?? '—'}
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
              caption={ceilingLow ? fa.mlEngine.confidenceCeilingLowNote : fa.mlEngine.confidenceCeilingNote}
              tone={ceilingLow ? 'warn' : 'neutral'}
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

        {ceilingLow && model && (
          <Alert tone="warn" className="mt-4">
            {fa.mlEngine.lowCeilingWarning}
          </Alert>
        )}
      </Card>

      {/* Confidence calibration: does confidence track win rate? */ }
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

      {/* Supported markets */ }
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
              {displayedMarkets.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-sm text-ink-faint">
                    {fa.mlEngine.noMarkets}
                  </td>
                </tr>
              ) : (
                displayedMarkets.map((market) => (
                  <MarketRow key={`${market.symbol}:${market.interval}:${market.modelVersion}`} market={market} />
                ))
              )}
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

        {!capsLoading && !hasMarkets && !capsError && (
          <p className="mt-4 text-xs text-ink-faint">{fa.mlEngine.noMarketsNote}</p>
        )}
      </Card>

      {/* Online learning: what the engine is learning from closed trades */ }
      <Card as="section" className="p-6 sm:p-7">
        <Eyebrow>{fa.mlEngine.onlineLearningLabel}</Eyebrow>
        <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
          {training?.onlineLearningEnabled === false
            ? fa.mlEngine.onlineLearningDisabled
            : fa.mlEngine.onlineLearningNote}
        </p>

        <div className="mt-4 -mx-1 -mx-5 sm:mx-0 sm:overflow-x-auto">
          <table className="w-full min-w-[36rem] border-collapse text-sm sm:min-w-0">
            <thead>
              <tr>
                <th className="text-start font-semibold">{fa.mlEngine.colMarket}</th>
                <th className="text-start font-semibold">{fa.mlEngine.colSamples}</th>
                <th className="text-start font-medium">{fa.mlEngine.colSinceTraining}</th>
                <th className="text-start font-semibold">{fa.mlEngine.colVerdict}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {!training || training.markets.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-sm text-ink-faint">
                    {fa.mlEngine.noOnlineMarkets}
                  </td>
                </tr>
              ) : (
                training.markets.map((market: MlMarketTrainingStatus) => {
                  const verdictTone: 'success' | 'warn' | 'danger' | undefined =
                    market.lastVerdict === 'promoted'
                      ? 'success'
                      : market.lastVerdict === 'rejected'
                        ? 'warn'
                        : market.lastVerdict === 'failed'
                          ? 'danger'
                          : undefined
                  const verdictLabel =
                    market.trainingInProgress
                      ? fa.mlEngine.trainingInProgress
                      : market.lastVerdict === 'promoted'
                        ? fa.mlEngine.verdictPromoted
                        : market.lastVerdict === 'rejected'
                          ? fa.mlEngine.verdictRejected
                          : market.lastVerdict === 'failed'
                            ? fa.mlEngine.verdictFailed
                            : '—'
                  return (
                    <tr key={`${market.symbol}:${market.interval}`}>
                      <td className="py-2.5 font-medium" dir="ltr">
                        {`${market.symbol} ${market.interval}`}
                      </td>
                      <td className="py-2.5 num">{market.samplesStored}</td>
                      <td className="py-2.5 num text-ink-muted">{market.samplesSinceTraining}</td>
                      <td className="py-2.5">
                        <span className="flex items-center gap-1.5">
                          {verdictTone && <StatusDot tone={verdictTone} />}
                          <span className={verdictTone === 'danger' ? 'text-danger' : ''} dir="auto">
                            {verdictLabel}
                          </span>
                        </span>
                      </td>
                    </tr>
                  )
                })
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
 * The `value` accepts ReactNode so a skeleton can be shown while loading.
 */
function StatValue({
  label,
  value,
  caption,
  tone = 'neutral',
}: {
  label: string
  value: string | React.ReactNode
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

/** A grey block matching the height of a loaded value, to keep the grid stable while fetching. */
function LoadingSkeleton({ width = 'w-20' }: { width?: string }) {
  return <span className={`inline-block h-5 animate-pulse rounded bg-line ${width}`} />
}
