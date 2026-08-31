import { useCallback, useState } from 'react'
import { PERMISSIONS, can } from '../auth/permissions'
import { useAuth } from '../auth/AuthContext'
import { PageHeader } from '../components/admin/PageHeader'
import { Alert } from '../components/ui/Alert'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Field } from '../components/ui/Field'
import { IconButton } from '../components/ui/IconButton'
import { Input } from '../components/ui/Input'
import { Modal } from '../components/ui/Modal'
import { Select } from '../components/ui/Select'
import { fa } from '../i18n/fa'
import { api } from '../lib/api'
import type { ExchangeConnection, ExchangeConnectionInput, MarketVenueName } from '../lib/apiTypes'
import { dateTimeText } from '../lib/tradingFormat'
import { useResource } from '../lib/useResource'

/**
 * Where API keys live: one row per (venue, account) the operator has connected.
 *
 * The screen is built around what it can never show. A key that can trade is itself a secret, so the
 * table carries only the last four characters — enough to tell two Binance keys apart, never enough to
 * trade with. Editing re-enters both halves of the pair, because a connection updated one-sided would
 * sign nothing and fail at tick time instead of here.
 *
 * Toggling a row inactive is the revocation path: bots pinned to it fault on their next tick rather
 * than placing orders on a key the operator just cut off. That asymmetry — instant off, deliberate on
 * — is stated on the confirmation.
 */

const VENUES: MarketVenueName[] = ['BinanceTestnet', 'BinanceFuturesTestnet', 'BinanceMainnet', 'Bitunix', 'Bybit']

type Dialog =
  | { kind: 'create' }
  | { kind: 'edit'; row: ExchangeConnection }
  | { kind: 'toggle'; row: ExchangeConnection }
  | { kind: 'delete'; row: ExchangeConnection }
  | null

export function ConnectionsPage() {
  const { session } = useAuth()

  const [dialog, setDialog] = useState<Dialog>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const fetcher = useCallback(
    (signal?: AbortSignal) => api.exchangeConnections.paged({ pageNumber: 1, pageSize: 200 }, signal),
    [],
  )
  const { data, error, isLoading, isRefreshing, refetch } = useResource(fetcher)

  const rows = data?.items ?? []
  const canCreate = can(session, PERMISSIONS.exchangeConnectionCreate)
  const canUpdate = can(session, PERMISSIONS.exchangeConnectionUpdate)
  const canDelete = can(session, PERMISSIONS.exchangeConnectionDelete)

  return (
    <div className="space-y-5">
      <PageHeader
        title={fa.connections.title}
        subtitle={fa.connections.subtitle}
        actions={
          canCreate && (
            <Button onClick={() => setDialog({ kind: 'create' })}>{fa.connections.createButton}</Button>
          )
        }
      />

      <Alert tone="info">
        {fa.connections.securityNote}
      </Alert>

      {notice && <Alert tone="success">{notice}</Alert>}

      <ConnectionsTable
        rows={rows}
        isLoading={isLoading}
        isRefreshing={isRefreshing}
        error={error}
        canUpdate={canUpdate}
        canDelete={canDelete}
        refetch={refetch}
        onEdit={(row) => setDialog({ kind: 'edit', row })}
        onToggle={(row) => setDialog({ kind: 'toggle', row })}
        onDelete={(row) => setDialog({ kind: 'delete', row })}
      />

      {dialog?.kind === 'create' && (
        <ConnectionFormModal
          isOpen
          onClose={() => setDialog(null)}
          onSaved={() => {
            setNotice(fa.connections.createdSuccess)
            refetch()
          }}
        />
      )}

      {dialog?.kind === 'edit' && (
        <ConnectionFormModal
          isOpen
          row={dialog.row}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setNotice(fa.connections.updatedSuccess)
            refetch()
          }}
        />
      )}

      {dialog?.kind === 'toggle' && (
        <ConfirmDialog
          isOpen
          onClose={() => setDialog(null)}
          confirmLabel={dialog.row.isActive ? fa.connections.deactivate : fa.connections.activate}
          tone={dialog.row.isActive ? 'danger' : 'primary'}
          title={dialog.row.isActive ? fa.connections.confirmDeactivateTitle : fa.connections.confirmActivateTitle}
          body={dialog.row.isActive ? fa.connections.confirmDeactivateBody : fa.connections.confirmActivateBody}
          onConfirm={async () => {
            await api.exchangeConnections.toggleActive(dialog.row.id)
            setNotice(dialog.row.isActive ? fa.connections.deactivatedSuccess : fa.connections.activatedSuccess)
            refetch()
          }}
        />
      )}

      {dialog?.kind === 'delete' && (
        <ConfirmDialog
          isOpen
          onClose={() => setDialog(null)}
          confirmLabel={fa.common.delete}
          title={fa.connections.confirmDeleteTitle}
          body={fa.connections.confirmDeleteBody}
          onConfirm={async () => {
            await api.exchangeConnections.remove(dialog.row.id)
            setNotice(fa.connections.deletedSuccess)
            refetch()
          }}
        />
      )}
    </div>
  )
}

function ConnectionsTable({
  rows,
  isLoading,
  isRefreshing,
  error,
  canUpdate,
  canDelete,
  refetch,
  onEdit,
  onToggle,
  onDelete,
}: {
  rows: ExchangeConnection[]
  isLoading: boolean
  isRefreshing: boolean
  error: string | null
  canUpdate: boolean
  canDelete: boolean
  refetch: () => void
  onEdit: (row: ExchangeConnection) => void
  onToggle: (row: ExchangeConnection) => void
  onDelete: (row: ExchangeConnection) => void
}) {
  const columns: Column<ExchangeConnection>[] = [
    {
      key: 'label',
      header: fa.connections.colLabel,
      cell: r => (
        <div className="space-y-0.5">
          <p className="font-medium text-ink">{r.label}</p>
          <p className="text-xs latin" dir="ltr">
            ••••{r.keyPreview}
          </p>
        </div>
      ),
    },
    {
      key: 'venue',
      header: fa.trading.venueLabel,
      cell: r => <span>{fa.trading.venue[r.venue] ?? r.venue}</span>,
    },
    {
      key: 'state',
      header: fa.connections.colState,
      cell: r =>
        r.isActive ? (
          <Badge tone="success">{fa.connections.stateActive}</Badge>
        ) : (
          <Badge tone="neutral">{fa.connections.stateInactive}</Badge>
        ),
    },
    {
      key: 'validated',
      header: fa.connections.colValidated,
      cell: r =>
        r.lastValidatedAt ? (
          <span className="num text-xs">{dateTimeText(r.lastValidatedAt)}</span>
        ) : (
          <span className="text-xs text-ink-faint">{fa.connections.neverValidated}</span>
        ),
    },
    {
      key: 'createdAt',
      header: fa.table.createdAt ?? '',
      cell: r => <span className="num text-xs">{dateTimeText(r.createdAt)}</span>,
    },
    ...(canUpdate || canDelete
      ? [
          {
            key: 'actions',
            header: '',
            className: 'w-px',
            cell: (r: ExchangeConnection) => (
              <div className="flex items-center gap-1">
                {canUpdate && (
                  <>
                    <IconButton label={fa.common.edit} onClick={() => onEdit(r)}>
                      ✎
                    </IconButton>
                    <IconButton label={r.isActive ? fa.connections.deactivate : fa.connections.activate} onClick={() => onToggle(r)}>
                      {r.isActive ? '⏹' : '▶'}
                    </IconButton>
                  </>
                )}
                {canDelete && (
                  <IconButton label={fa.common.delete} onClick={() => onDelete(r)}>
                    🗑
                  </IconButton>
                )}
              </div>
            ),
          } satisfies Column<ExchangeConnection>,
        ]
      : []),
  ]

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={r => r.id}
      isLoading={isLoading}
      isRefreshing={isRefreshing}
      error={error}
      emptyTitle={fa.connections.emptyTitle}
      emptyBody={fa.connections.emptyBody}
      // A failed refetch keeps stale rows visible; an explicit retry is still worth offering.
      skeletonRows={4}
    />
  )
}

function ConnectionFormModal({
  isOpen,
  onClose,
  onSaved,
  row,
}: {
  isOpen: boolean
  onClose: () => void
  onSaved: () => void
  /** Present means edit; both secrets must be re-entered. */
  row?: ExchangeConnection
}) {
  const isEdit = !!row

  const [venue, setVenue] = useState<MarketVenueName>(row?.venue ?? 'BinanceTestnet')
  const [label, setLabel] = useState(row?.label ?? '')
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)

  const submit = async () => {
    if (!label.trim()) {
      setValidationError(fa.connections.labelRequired)
      return
    }
    if (!apiKey.trim() || !apiSecret.trim()) {
      setValidationError(fa.connections.secretsRequired)
      return
    }

    const payload: ExchangeConnectionInput = {
      venue,
      label: label.trim(),
      apiKey: apiKey.trim(),
      apiSecret: apiSecret.trim(),
    }

    if (isEdit && row) await api.exchangeConnections.update(row.id, payload)
    else await api.exchangeConnections.create(payload)

    onSaved()
    onClose()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEdit ? fa.connections.editTitle : fa.connections.createTitle}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {fa.common.cancel}
          </Button>
          <Button onClick={() => void submit()}>{fa.common.save}</Button>
        </>
      }
    >
      <div className="space-y-4">
        {validationError && <Alert tone="error">{validationError}</Alert>}

        <Field label={fa.trading.venueLabel} required>
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

        <Field label={fa.connections.colLabel} hint={fa.connections.labelHint} required>
          {ids => <Input {...ids} value={label} onChange={e => setLabel(e.target.value)} />}
        </Field>

        <Field
          label={fa.connections.apiKey}
          hint={isEdit ? fa.connections.reenterHint : undefined}
          required
        >
          {ids => <Input {...ids} value={apiKey} onChange={e => setApiKey(e.target.value)} autoComplete="off" />}
        </Field>

        <Field
          label={fa.connections.apiSecret}
          hint={isEdit ? fa.connections.reenterHint : fa.connections.apiSecretHint}
          required
        >
          {ids => (
            <Input
              {...ids}
              type="password"
              value={apiSecret}
              onChange={e => setApiSecret(e.target.value)}
              autoComplete="new-password"
            />
          )}
        </Field>

        <Alert tone="warn">{fa.connections.writeOnceNote}</Alert>
      </div>
    </Modal>
  )
}
