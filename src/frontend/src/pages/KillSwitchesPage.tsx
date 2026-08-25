import { useCallback, useState } from 'react'
import { PERMISSIONS, can } from '../auth/permissions'
import { useAuth } from '../auth/AuthContext'
import { FilterBar } from '../components/admin/FilterBar'
import { PageHeader } from '../components/admin/PageHeader'
import { Alert } from '../components/ui/Alert'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Input } from '../components/ui/Input'
import { Select } from '../components/ui/Select'
import { Pagination } from '../components/ui/Pagination'
import { KillSwitchStateBadge, scopeLabel } from '../components/trading/TradingBadges'
import { fa } from '../i18n/fa'
import { api } from '../lib/api'
import type { KillSwitch, KillSwitchInput, KillSwitchScopeName, KillSwitchFilters } from '../lib/apiTypes'
import { dateTimeText } from '../lib/tradingFormat'
import { useResource } from '../lib/useResource'

/**
 * The kill-switch listing: see engaged switches, engage a new one, disengage.
 *
 * Engaging blocks new intents; it does not cancel resting orders or close positions.
 * That distinction is written on every engage dialog.
 */

type Dialog =
  | { kind: 'engage' }
  | { kind: 'disengage'; killSwitch: KillSwitch }
  | null

const SCOPES: (KillSwitchScopeName | '')[] = ['', 'Global', 'OperatingMode', 'Exchange', 'Bot', 'Symbol']

export function KillSwitchesPage() {
  const { session } = useAuth()

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [engagedOnly, setEngagedOnly] = useState(false)

  const [dialog, setDialog] = useState<Dialog>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // Engage form state
  const [scope, setScope] = useState<KillSwitchScopeName>('Global')
  const [scopeOperatingMode, setScopeOperatingMode] = useState<'Paper' | 'Sandbox' | 'Live' | ''>('')
  const [scopeSymbol, setScopeSymbol] = useState('')
  const [scopeBotId, setScopeBotId] = useState('')
  const [reason, setReason] = useState('')

  // Disengage reason
  const [disengageReason, setDisengageReason] = useState('')

  const filters: KillSwitchFilters = {
    ...(engagedOnly && { engagedOnly: true }),
  }

  const fetcher = useCallback(
    (signal?: AbortSignal) => api.killSwitches.paged({ pageNumber: page, pageSize }, filters, signal),
    [page, pageSize, engagedOnly]
  )

  const { data, error, isLoading, isRefreshing, refetch } = useResource(fetcher)

  const switches = data?.items ?? []
  const totalRecords = data?.totalRecords ?? 0

  const canEngage = can(session, PERMISSIONS.killSwitchEngage)
  const canDisengage = can(session, PERMISSIONS.killSwitchDisengage)

  const handleEngage = useCallback(async () => {
    if (!reason.trim()) return

    const input: KillSwitchInput = {
      scope,
      reason,
      ...(scope === 'OperatingMode' && scopeOperatingMode && { scopeOperatingMode }),
      ...(scope === 'Symbol' && scopeSymbol && { scopeSymbol }),
      ...(scope === 'Bot' && scopeBotId && { scopeBotId }),
    }

    try {
      await api.killSwitches.engage(input)
      setNotice(fa.killSwitches.engagedSuccess)
      setDialog(null)
      setReason('')
      setScope('Global')
      setScopeOperatingMode('')
      setScopeSymbol('')
      setScopeBotId('')
      refetch()
    } catch (e) {
      console.error(e)
    }
  }, [scope, scopeOperatingMode, scopeSymbol, scopeBotId, reason, refetch])

  const handleDisengage = useCallback(async () => {
    if (!dialog || dialog.kind !== 'disengage') return
    if (!disengageReason.trim()) return

    try {
      await api.killSwitches.disengage(dialog.killSwitch.id, { reason: disengageReason })
      setNotice(fa.killSwitches.disengagedSuccess)
      setDialog(null)
      setDisengageReason('')
      refetch()
    } catch (e) {
      console.error(e)
    }
  }, [dialog, disengageReason, refetch])

  const columns: Column<KillSwitch>[] = [
    {
      key: 'scope',
      header: fa.killSwitches.colScope,
      cell: sw => (
        <div className="space-y-1">
          <p className="font-medium text-ink">{scopeLabel(sw.scope)}</p>
          {sw.scopeOperatingMode && (
            <p className="text-xs text-ink-faint">{sw.scopeOperatingMode}</p>
          )}
          {sw.scopeSymbol && (
            <p className="text-xs text-ink-faint">{sw.scopeSymbol}</p>
          )}
        </div>
      ),
    },
    {
      key: 'state',
      header: fa.killSwitches.colState,
      cell: sw => <KillSwitchStateBadge isEngaged={sw.isEngaged} />,
    },
    {
      key: 'reason',
      header: fa.killSwitches.colReason,
      cell: sw => (
        <p className="text-sm text-ink-soft max-w-xs truncate" title={sw.reason}>
          {sw.reason}
        </p>
      ),
    },
    {
      key: 'engagedBy',
      header: fa.killSwitches.colEngagedBy,
      cell: sw => (
        <div className="space-y-1">
          <p className="text-sm text-ink">
            {sw.engagedByUserName ?? (sw.isAutomatic ? fa.killSwitches.automatic : '—')}
          </p>
          {sw.isAutomatic && (
            <p className="text-xs text-ink-faint">{fa.killSwitches.automaticNote}</p>
          )}
        </div>
      ),
    },
    {
      key: 'engagedAt',
      header: fa.killSwitches.colEngagedAt,
      cell: sw => <span className="num text-ink-soft">{dateTimeText(sw.engagedAt)}</span>,
    },
    {
      key: 'actions',
      header: '',
      className: 'w-px',
      cell: sw => {
        if (!sw.isEngaged || !canDisengage) return null

        return (
          <Button
            size="sm"
            variant="danger"
            onClick={() => setDialog({ kind: 'disengage', killSwitch: sw })}
          >
            {fa.killSwitches.disengage}
          </Button>
        )
      },
    },
  ]

  return (
    <div className="space-y-5">
      <PageHeader
        title={fa.killSwitches.title}
        subtitle={fa.killSwitches.subtitle}
        actions={
          canEngage && (
            <Button variant="danger" onClick={() => setDialog({ kind: 'engage' })}>
              {fa.killSwitches.engageButton}
            </Button>
          )
        }
      />

      <Alert tone="warn">
        {fa.killSwitches.scopeNote}
      </Alert>

      <FilterBar isFiltered={engagedOnly} onClear={() => setEngagedOnly(false)}>
        <label className="flex items-center gap-2 text-sm text-ink-soft">
          <input
            type="checkbox"
            checked={engagedOnly}
            onChange={e => {
              setEngagedOnly(e.target.checked)
              setPage(1)
            }}
            className="rounded border-line"
          />
          {fa.killSwitches.filterEngagedOnly}
        </label>
      </FilterBar>

      {notice && (
        <Alert tone="success">
          {notice}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={switches}
        rowKey={sw => sw.id}
        isLoading={isLoading}
        isRefreshing={isRefreshing}
        error={error}
        emptyTitle={fa.killSwitches.emptyTitle}
        emptyBody={fa.killSwitches.emptyBody}
      />

      <Pagination
        page={page}
        pageSize={pageSize}
        totalRecords={totalRecords}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
        isBusy={isLoading || isRefreshing}
      />

      {/* Engage dialog */}
      {dialog?.kind === 'engage' && (
        <ConfirmDialog
          isOpen
          onClose={() => {
            setDialog(null)
            setReason('')
            setScope('Global')
          }}
          title={fa.killSwitches.confirmEngageTitle}
          confirmLabel={fa.killSwitches.engageButton}
          tone="danger"
          onConfirm={handleEngage}
          body={
            <div className="space-y-4">
              <p>{fa.killSwitches.confirmEngageBody}</p>

              <div className="space-y-2">
                <label className="block text-sm font-medium text-ink-soft">
                  {fa.killSwitches.scope} <span className="text-danger">*</span>
                </label>
                <Select value={scope} onChange={e => setScope(e.target.value as KillSwitchScopeName)}>
                  {SCOPES.filter(Boolean).map(s => (
                    <option key={s} value={s}>
                      {scopeLabel(s!)}
                    </option>
                  ))}
                </Select>
                <p className="text-xs text-ink-faint">{fa.killSwitches.scopeHint}</p>
              </div>

              {scope === 'OperatingMode' && (
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-ink-soft">
                    {fa.killSwitches.scopeModeField}
                  </label>
                  <Select
                    value={scopeOperatingMode}
                    onChange={e => setScopeOperatingMode(e.target.value as 'Paper' | 'Sandbox' | 'Live' | '')}
                  >
                    <option value="">—</option>
                    <option value="Paper">Paper</option>
                    <option value="Sandbox">Sandbox</option>
                    <option value="Live">Live</option>
                  </Select>
                </div>
              )}

              {scope === 'Symbol' && (
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-ink-soft">
                    {fa.killSwitches.scopeSymbolField}
                  </label>
                  <Input
                    value={scopeSymbol}
                    onChange={e => setScopeSymbol(e.target.value.toUpperCase())}
                    placeholder="BTCUSDT"
                  />
                </div>
              )}

              {scope === 'Bot' && (
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-ink-soft">
                    {fa.killSwitches.scopeBotField}
                  </label>
                  <Input
                    value={scopeBotId}
                    onChange={e => setScopeBotId(e.target.value)}
                    placeholder="GUID"
                  />
                </div>
              )}

              <div className="space-y-2">
                <label className="block text-sm font-medium text-ink-soft">
                  {fa.killSwitches.reason} <span className="text-danger">*</span>
                </label>
                <Input
                  value={reason}
                  onChange={e => setReason(e.target.value)}
                  placeholder={fa.killSwitches.reasonHint}
                />
              </div>
            </div>
          }
        />
      )}

      {/* Disengage dialog */}
      {dialog?.kind === 'disengage' && (
        <ConfirmDialog
          isOpen
          onClose={() => {
            setDialog(null)
            setDisengageReason('')
          }}
          title={fa.killSwitches.confirmDisengageTitle}
          confirmLabel={fa.killSwitches.disengage}
          tone="primary"
          onConfirm={handleDisengage}
          body={
            <div className="space-y-4">
              <p>{fa.killSwitches.confirmDisengageBody}</p>

              <div className="rounded-lg bg-surface-muted p-3 text-sm">
                <p>
                  <span className="text-ink-soft">{fa.killSwitches.scope}: </span>
                  <span className="font-medium text-ink">{scopeLabel(dialog.killSwitch.scope)}</span>
                </p>
                <p>
                  <span className="text-ink-soft">{fa.killSwitches.reason}: </span>
                  <span className="text-ink">{dialog.killSwitch.reason}</span>
                </p>
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-medium text-ink-soft">
                  {fa.killSwitches.disengageReason} <span className="text-danger">*</span>
                </label>
                <Input
                  value={disengageReason}
                  onChange={e => setDisengageReason(e.target.value)}
                  placeholder={fa.killSwitches.disengageReasonHint}
                />
              </div>
            </div>
          }
        />
      )}
    </div>
  )
}