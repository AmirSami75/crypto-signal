import { useCallback, useState } from 'react'
import { Link } from 'react-router'
import { PERMISSIONS, can } from '../auth/permissions'
import { useAuth } from '../auth/AuthContext'
import { FilterBar } from '../components/admin/FilterBar'
import { PageHeader } from '../components/admin/PageHeader'
import { Alert } from '../components/ui/Alert'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { DataTable, type Column } from '../components/ui/DataTable'
import { IconButton } from '../components/ui/IconButton'
import { Pagination } from '../components/ui/Pagination'
import { Select } from '../components/ui/Select'
import { Input } from '../components/ui/Input'
import { BotStatusBadge, OperatingModeBadge } from '../components/trading/TradingBadges'
import { BotFormModal } from '../components/trading/BotFormModal'
import { fa } from '../i18n/fa'
import { api } from '../lib/api'
import type { BotDetail, BotSummary, BotFilters, BotStatusName, OperatingModeName } from '../lib/apiTypes'
import { ROUTES, botDetailPath, botMonitorPath } from '../routes'
import { dateTimeText, signedMoneyText } from '../lib/tradingFormat'
import { useDebounced } from '../lib/useDebounced'
import { useResource } from '../lib/useResource'

/**
 * The bot listing: filter, page, create, and status changes.
 *
 * Start is the authorization moment — the platform gates all run there, not at create time.
 * Operating mode is prominent on every row and inside every confirmation dialog.
 */

type Dialog =
  | { kind: 'create' }
  | { kind: 'edit'; bot: BotSummary }
  | { kind: 'start'; bot: BotSummary }
  | { kind: 'pause'; bot: BotSummary }
  | { kind: 'stop'; bot: BotSummary }
  | { kind: 'delete'; bot: BotSummary }
  | null

type ConfirmKind = 'start' | 'pause' | 'stop' | 'delete'

const STATUSES: (BotStatusName | '')[] = ['', 'Draft', 'Active', 'Paused', 'Stopped', 'Faulted']
const MODES: (OperatingModeName | '')[] = ['', 'Paper', 'Sandbox', 'Live']

export function BotsPage() {
  const { session } = useAuth()

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  const [symbolFilter, setSymbolFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<BotStatusName | ''>('')
  const [modeFilter, setModeFilter] = useState<OperatingModeName | ''>('')

  const [dialog, setDialog] = useState<Dialog>(null)
  const [reason, setReason] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  // The full record behind an 'edit' dialog. Fetched on open — the listing row is a summary and does
  // not carry every field the form seeds from (risk limits, expected model version).
  const [editDetail, setEditDetail] = useState<BotDetail | null>(null)

  const debouncedSymbol = useDebounced(symbolFilter)

  // Serialized rather than an object literal in deps: a fresh `{}` every render would give the
  // fetcher a new identity each render, and useResource would refetch on every render — the page
  // would tick forever and the pagination controls would flicker enabled/disabled.
  const filterKey = [debouncedSymbol, statusFilter, modeFilter].filter(Boolean).join('|')

  const fetcher = useCallback(
    (signal?: AbortSignal) =>
      api.bots.paged(
        { pageNumber: page, pageSize },
        {
          ...(debouncedSymbol && { symbol: debouncedSymbol }),
          ...(statusFilter && { status: statusFilter }),
          ...(modeFilter && { operatingMode: modeFilter }),
        },
        signal,
      ),
    [page, pageSize, filterKey]
  )

  const { data, error, isLoading, isRefreshing, refetch } = useResource(fetcher)

  const bots = data?.items ?? []
  const totalRecords = data?.totalRecords ?? 0

  // Permission checks
  const canCreate = can(session, PERMISSIONS.botCreate)
  const canEdit = can(session, PERMISSIONS.botUpdate)
  const canStart = can(session, PERMISSIONS.botStart)
  const canPause = can(session, PERMISSIONS.botPause)
  const canStop = can(session, PERMISSIONS.botStop)
  const canDelete = can(session, PERMISSIONS.botDelete)

  const isFiltered = !!(debouncedSymbol || statusFilter || modeFilter)

  const clearFilters = useCallback(() => {
    setSymbolFilter('')
    setStatusFilter('')
    setModeFilter('')
  }, [])

  const handleConfirm = useCallback(async () => {
    if (!dialog || dialog.kind === 'create' || dialog.kind === 'edit') return

    const { kind, bot } = dialog

    if (kind !== 'delete' && !reason.trim()) {
      return // reason required for start/pause/stop
    }

    try {
      if (kind === 'start') {
        await api.bots.start(bot.id, { reason })
        setNotice(fa.bots.startedSuccess)
      } else if (kind === 'pause') {
        await api.bots.pause(bot.id, { reason })
        setNotice(fa.bots.pausedSuccess)
      } else if (kind === 'stop') {
        await api.bots.stop(bot.id, { reason })
        setNotice(fa.bots.stoppedSuccess)
      } else if (kind === 'delete') {
        await api.bots.remove(bot.id)
        setNotice(fa.bots.deletedSuccess)
      }
      setDialog(null)
      setReason('')
      refetch()
    } catch (e) {
      console.error(e)
    }
  }, [dialog, reason, refetch])

  const openEdit = useCallback(
    async (bot: BotSummary) => {
      try {
        const detail = await api.bots.byId(bot.id)
        setEditDetail(detail)
        setDialog({ kind: 'edit', bot })
      } catch (e) {
        console.error(e)
      }
    },
    [],
  )

  const CONFIRMS: Record<
    ConfirmKind,
    {
      title: string
      body: string
      confirmLabel: string
      tone: 'danger' | 'primary'
      needsReason: boolean
    }
  > = {
    start: {
      title: fa.bots.confirmStartTitle,
      body: fa.bots.confirmStartBody,
      confirmLabel: fa.bots.start,
      tone: 'primary',
      needsReason: true,
    },
    pause: {
      title: fa.bots.confirmPauseTitle,
      body: fa.bots.confirmPauseBody,
      confirmLabel: fa.bots.pause,
      tone: 'primary',
      needsReason: true,
    },
    stop: {
      title: fa.bots.confirmStopTitle,
      body: fa.bots.confirmStopBody,
      confirmLabel: fa.bots.stop,
      tone: 'danger',
      needsReason: true,
    },
    delete: {
      title: fa.bots.confirmDeleteTitle,
      body: fa.bots.confirmDeleteBody,
      confirmLabel: fa.bots.deleteBot,
      tone: 'danger',
      needsReason: false,
    },
  }

  const columns: Column<BotSummary>[] = [
    {
      key: 'name',
      header: fa.bots.colBot,
      cell: bot => (
        <div className="space-y-1">
          <Link to={botDetailPath(bot.id)} className="font-medium text-ink hover:text-accent">
            {bot.name}
          </Link>
          <p className="text-xs text-ink-faint">{bot.symbol}</p>
        </div>
      ),
    },
    {
      key: 'market',
      header: fa.bots.colMarket,
      cell: bot => (
        <div className="space-y-1">
          <p className="text-sm text-ink">{bot.symbol}</p>
          <p className="text-xs text-ink-faint">{bot.interval}</p>
        </div>
      ),
    },
    {
      key: 'mode',
      header: fa.bots.colMode,
      cell: bot => <OperatingModeBadge mode={bot.operatingMode} />,
    },
    {
      key: 'status',
      header: fa.bots.colStatus,
      cell: bot => (
        <div className="space-y-1">
          <BotStatusBadge status={bot.status} />
          {bot.isBlockedByKillSwitch && (
            <p className="text-xs text-danger">{fa.trading.killSwitchBlocked}</p>
          )}
        </div>
      ),
    },
    {
      key: 'position',
      header: fa.bots.colPosition,
      cell: bot =>
        bot.openPositionCount > 0 ? (
          <Badge tone="accent">{fa.bots.openPositions}</Badge>
        ) : (
          <span className="text-ink-faint">{fa.bots.noOpenPosition}</span>
        ),
    },
    {
      key: 'pnl',
      header: fa.bots.colPnl,
      cell: bot => (
        <span className={`num font-medium ${bot.realizedPnl >= 0 ? 'text-success' : 'text-danger'}`}>
          {signedMoneyText(bot.realizedPnl)}
        </span>
      ),
    },
    {
      key: 'lastTick',
      header: fa.bots.colLastTick,
      cell: bot => (
        <span className="text-ink-faint">
          {bot.lastTickAt ? dateTimeText(bot.lastTickAt) : fa.bots.neverTicked}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-px',
      cell: bot => {
        const isDraft = bot.status === 'Draft'
        const isActive = bot.status === 'Active'
        const isPaused = bot.status === 'Paused'
        const isStopped = bot.status === 'Stopped'
        const isFaulted = bot.status === 'Faulted'

        return (
          <div className="flex items-center gap-1">
            <Link to={botMonitorPath(bot.id)} title={fa.monitor.title}>
              <IconButton label={fa.monitor.title}>◉</IconButton>
            </Link>
            {(isDraft || isPaused || isStopped) && canEdit && (
              <IconButton label={fa.common.edit} onClick={() => void openEdit(bot)}>
                ✎
              </IconButton>
            )}
            {(isDraft || isPaused || isStopped || isFaulted) && canStart && (
              <IconButton
                label={fa.bots.start}
                onClick={() => setDialog({ kind: 'start', bot })}
              >
                ▶
              </IconButton>
            )}
            {isActive && canPause && (
              <IconButton
                label={fa.bots.pause}
                onClick={() => setDialog({ kind: 'pause', bot })}
              >
                ⏸
              </IconButton>
            )}
            {(isActive || isPaused || isFaulted) && canStop && (
              <IconButton
                label={fa.bots.stop}
                onClick={() => setDialog({ kind: 'stop', bot })}
              >
                ⏹
              </IconButton>
            )}
            {(isDraft || isStopped) && canDelete && (
              <IconButton
                label={fa.bots.deleteBot}
                onClick={() => setDialog({ kind: 'delete', bot })}
              >
                🗑
              </IconButton>
            )}
          </div>
        )
      },
    },
  ]

  const confirmConfig =
    dialog && dialog.kind !== 'create' && dialog.kind !== 'edit' ? CONFIRMS[dialog.kind] : null

  return (
    <div className="space-y-5">
      <PageHeader
        title={fa.bots.title}
        subtitle={fa.bots.subtitle}
        actions={
          canCreate && (
            <Button onClick={() => setDialog({ kind: 'create' })}>{fa.bots.createButton}</Button>
          )
        }
      />

      <Alert tone="info">
        {fa.trading.evidenceNote}
      </Alert>

      <FilterBar isFiltered={isFiltered} onClear={clearFilters}>
        <Input
          placeholder={fa.bots.filterSymbol}
          value={symbolFilter}
          onChange={e => setSymbolFilter(e.target.value)}
          className="w-40"
        />
        <Select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value as BotStatusName | '')}
          className="w-32"
        >
          {STATUSES.map(s => (
            <option key={s} value={s}>
              {s ? (fa.trading.botStatus[s] ?? s) : fa.common.all}
            </option>
          ))}
        </Select>
        <Select
          value={modeFilter}
          onChange={e => setModeFilter(e.target.value as OperatingModeName | '')}
          className="w-32"
        >
          {MODES.map(m => (
            <option key={m} value={m}>
              {m ? (fa.trading.modeLabel ?? m) : fa.common.all}
            </option>
          ))}
        </Select>
      </FilterBar>

      {notice && (
        <Alert tone="success">
          {notice}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={bots}
        rowKey={bot => bot.id}
        isLoading={isLoading}
        isRefreshing={isRefreshing}
        error={error}
        emptyTitle={fa.bots.emptyTitle}
        emptyBody={fa.bots.emptyBody}
      />

      <Pagination
        page={page}
        pageSize={pageSize}
        totalRecords={totalRecords}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
        isBusy={isLoading || isRefreshing}
      />

      {/* Create / edit modal. Edit needs the full record, so the listing row is re-fetched by id
          rather than trusting the paged summary to carry every field the form seeds from. */}
      {dialog && (dialog.kind === 'create' || dialog.kind === 'edit') && (
        <BotFormModal
          isOpen
          onClose={() => setDialog(null)}
          onSaved={() => {
            setNotice(dialog.kind === 'create' ? fa.bots.createdSuccess : fa.bots.updatedSuccess)
            refetch()
          }}
          bot={dialog.kind === 'edit' ? editDetail : undefined}
        />
      )}

      {/* Confirm dialog for status changes */}
      {confirmConfig && dialog && dialog.kind !== 'create' && dialog.kind !== 'edit' && (
        <ConfirmDialog
          isOpen
          onClose={() => {
            setDialog(null)
            setReason('')
          }}
          title={confirmConfig.title}
          confirmLabel={confirmConfig.confirmLabel}
          tone={confirmConfig.tone}
          onConfirm={handleConfirm}
          body={
            <div className="space-y-4">
              <p>{confirmConfig.body}</p>

              {/* Operating mode badge - prominent in every confirmation */}
              <div className="flex items-center gap-2">
                <span className="text-sm text-ink-soft">{fa.trading.modeLabel}:</span>
                <OperatingModeBadge mode={dialog.bot.operatingMode} />
              </div>

              {confirmConfig.needsReason && (
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-ink-soft">
                    {fa.bots.reason} <span className="text-danger">*</span>
                  </label>
                  <Input
                    value={reason}
                    onChange={e => setReason(e.target.value)}
                    placeholder={fa.bots.reasonHint}
                  />
                </div>
              )}
            </div>
          }
        />
      )}
    </div>
  )
}
