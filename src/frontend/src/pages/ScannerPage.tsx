import { useCallback, useEffect, useState } from 'react'
import { fa } from '../i18n/fa'
import { api } from '../lib/api'
import { useResource } from '../lib/useResource'
import { useDebounced } from '../lib/useDebounced'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Pagination } from '../components/ui/Pagination'
import { Card, Eyebrow } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { DirectionBadge } from '../components/trading/TradingBadges'
import type { ScannerSignal } from '../lib/apiTypes'

/**
 * The market scanner: strategy-zoo proposals, newest first. Every row is a proposal only —
 * trading one is the operator's act of creating and starting a bot from it.
 */
export function ScannerPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  const [symbolFilter, setSymbolFilter] = useState('')
  const [strategyFilter, setStrategyFilter] = useState('')
  const debouncedSymbol = useDebounced(symbolFilter)
  const debouncedStrategy = useDebounced(strategyFilter)

  // Serialized rather than an object literal in deps: a fresh object each render would change the
  // fetcher's identity every render and refetch forever (same discipline as BotsPage).
  const filterKey = [debouncedSymbol, debouncedStrategy].filter(Boolean).join('|')

  const fetcher = useCallback(
    (signal?: AbortSignal) =>
      api.scanner.paged(
        { pageNumber: page, pageSize },
        {
          ...(debouncedSymbol && { symbol: debouncedSymbol.toUpperCase() }),
          ...(debouncedStrategy && { strategy: debouncedStrategy }),
        },
        signal,
      ),
    [page, pageSize, filterKey],
  )

  const { data, error, isLoading, isRefreshing, refetch } = useResource(fetcher)

  const signals = data?.items ?? []
  const totalRecords = data?.totalRecords ?? 0
  const isFiltered = !!(debouncedSymbol || debouncedStrategy)

  const clearFilters = useCallback(() => {
    setSymbolFilter('')
    setStrategyFilter('')
  }, [])

  // Keep pagination honest when the search changes.
  const prevFilterKey = useDebounced(filterKey)
  useEffect(() => {
    setPage(1)
    // Only the debounced aggregate matters — raw keystrokes should not reset.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prevFilterKey])

  const columns: Column<ScannerSignal>[] = [
    {
      key: 'symbol',
      header: fa.scanner.symbol,
      cell: s => <span className="font-mono">{s.symbol}</span>,
    },
    { key: 'strategy', header: fa.scanner.strategy, cell: s => s.strategyKey },
    {
      key: 'direction',
      header: fa.scanner.direction,
      cell: s => <DirectionBadge direction={s.direction} />,
    },
    {
      key: 'confidence',
      header: fa.scanner.confidence,
      cell: s => <span className="num">{`${(s.confidence * 100).toFixed(1)}%`}</span>,
    },
    {
      key: 'score',
      header: fa.scanner.score,
      cell: s => s.score.toFixed(2),
    },
    {
      key: 'atr',
      header: fa.scanner.atr,
      cell: s => <span className="num">{Number(s.atrAtSignal).toFixed(2)}</span>,
    },
    {
      key: 'reason',
      header: fa.scanner.reason,
      cell: s => <span title={s.reason}>{s.reason}</span>,
    },
    {
      key: 'createdAt',
      header: fa.scanner.age,
      cell: s => (
        <span title={new Date(s.createdAt).toLocaleString()}>{formatAge(s.createdAt)}</span>
      ),
    },
  ]

  return (
    <Card>
      <Eyebrow>{fa.scanner.title}</Eyebrow>
      <p className="mb-4 text-sm opacity-70">{fa.scanner.subtitle}</p>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="space-y-2">
          <label className="block text-sm font-medium text-ink-soft">
            {fa.scanner.symbolFilter}
          </label>
          <Input
            value={symbolFilter}
            onChange={e => setSymbolFilter(e.target.value)}
            placeholder="BTCUSDT"
          />
        </div>
        <div className="space-y-2">
          <label className="block text-sm font-medium text-ink-soft">
            {fa.scanner.strategyFilter}
          </label>
          <Input
            value={strategyFilter}
            onChange={e => setStrategyFilter(e.target.value)}
            placeholder="rsi"
          />
        </div>
        {isFiltered && (
          <button type="button" className="text-sm underline" onClick={clearFilters}>
            {fa.scanner.clearFilters}
          </button>
        )}
      </div>

      <DataTable
        columns={columns}
        rows={signals}
        rowKey={s => s.id}
        isLoading={isLoading}
        isRefreshing={isRefreshing}
        error={error}
        emptyTitle={fa.scanner.emptyTitle}
        emptyBody={fa.scanner.emptyBody}
      />

      <Pagination
        page={page}
        pageSize={pageSize}
        totalRecords={totalRecords}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
        isBusy={isLoading || isRefreshing}
      />
    </Card>
  )
}

/** Compact relative age, e.g. "4 minutes" — from the row's creation stamp. */
function formatAge(createdAt: string): string {
  const elapsed = Date.now() - new Date(createdAt).getTime()
  const minutes = Math.floor(elapsed / 60_000)
  if (minutes < 1) return fa.scanner.justNow
  if (minutes < 60) return `${minutes} ${fa.scanner.minutesAgo}`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} ${fa.scanner.hoursAgo}`
  return `${Math.floor(hours / 24)} ${fa.scanner.daysAgo}`
}
