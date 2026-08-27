import { useCallback, useEffect, useState } from 'react'
import { Checkbox } from '../ui/Checkbox'
import { Field } from '../ui/Field'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'
import { Button } from '../ui/Button'
import { Alert } from '../ui/Alert'
import { Modal } from '../ui/Modal'
import { fa } from '../../i18n/fa'
import { api, errorMessage } from '../../lib/api'
import type { ExchangeConnection } from '../../lib/apiTypes'
import type {
  BotDetail,
  BotInput,
  MarketVenueName,
  OperatingModeName,
} from '../../lib/apiTypes'

/**
 * Create and edit one bot.
 *
 * The form is split into the four sections the i18n file names — identity, market, strategy,
 * limits — because twenty-odd fields in one column reads as a wall. The section boundaries are also
 * where the two safety notes live: `marketLocked` under the market grid (those fields are create-only
 * server-side) and `limitsNote` at the foot of the risk section, where the zero-means-deny inversion
 * is stated next to the numbers it governs.
 *
 * Editing reuses the same payload type as creating (`BotInput`), but three of its fields arrive
 * disabled: the server refuses to change a bot's `symbol`, `interval`, or `operatingMode` after
 * creation, so the form never pretends otherwise.
 */

const INTERVALS = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w']
const VENUES: MarketVenueName[] = ['Replay', 'BinanceTestnet', 'BinanceMainnet']
const MODES: OperatingModeName[] = ['Paper', 'Sandbox', 'Live']

/** Every numeric field starts empty rather than at zero — see `NUMERIC_FIELDS`. */
type FormState = {
  name: string
  description: string
  symbol: string
  interval: string
  venue: MarketVenueName
  operatingMode: OperatingModeName
  takeProfitPercent: string
  stopLossPercent: string
  allowShort: boolean
  leverage: string
  quoteNotionalPerTrade: string
  minimumConfidence: string
  maxHoldingPeriods: string
  cadenceSeconds: string
  maxOrderNotional: string
  maxPositionNotional: string
  maxDailyLoss: string
  maxDrawdown: string
  maxConcurrentPositions: string
  maxOrdersPerDay: string
  maxConsecutiveFailures: string
  maxSlippageBps: string
  expectedModelVersion: string
  exchangeConnectionId: string
}

const EMPTY_FORM: FormState = {
  name: '',
  description: '',
  symbol: 'BTCUSDT',
  interval: '1h',
  venue: 'BinanceTestnet',
  operatingMode: 'Paper',
  takeProfitPercent: '',
  stopLossPercent: '',
  allowShort: false,
  leverage: '1',
  quoteNotionalPerTrade: '',
  minimumConfidence: '',
  maxHoldingPeriods: '',
  cadenceSeconds: '',
  maxOrderNotional: '',
  maxPositionNotional: '',
  maxDailyLoss: '',
  maxDrawdown: '',
  maxConcurrentPositions: '',
  maxOrdersPerDay: '',
  maxConsecutiveFailures: '',
  maxSlippageBps: '',
  expectedModelVersion: '',
  exchangeConnectionId: '',
}

/** The form keys that render through `numberField` — every one is a numeric *string* field, and each
 *  also names a `fa.bots` entry for its label (plus an optional `<key>Hint`). */
type NumericFieldKey =
  | 'takeProfitPercent'
  | 'stopLossPercent'
  | 'leverage'
  | 'quoteNotionalPerTrade'
  | 'minimumConfidence'
  | 'maxHoldingPeriods'
  | 'cadenceSeconds'
  | 'maxOrderNotional'
  | 'maxPositionNotional'
  | 'maxDailyLoss'
  | 'maxDrawdown'
  | 'maxConcurrentPositions'
  | 'maxOrdersPerDay'
  | 'maxConsecutiveFailures'
  | 'maxSlippageBps'

/** Numeric fields that must parse to a positive number when filled; blanks send nothing where the
 *  API allows absence, and the risk limits are validated by the server's fail-closed rules anyway. */
const POSITIVE_NUMBERS = [
  'takeProfitPercent',
  'stopLossPercent',
  'quoteNotionalPerTrade',
] as const

function fromDetail(bot: BotDetail): FormState {
  const num = (value: number | null | undefined) => (value === null || value === undefined ? '' : String(value))
  return {
    name: bot.name,
    description: bot.description ?? '',
    symbol: bot.symbol,
    interval: bot.interval,
    venue: bot.venue,
    operatingMode: bot.operatingMode,
    takeProfitPercent: num(bot.takeProfitPercent),
    stopLossPercent: num(bot.stopLossPercent),
    allowShort: bot.allowShort,
    leverage: num(bot.leverage ?? 1),
    quoteNotionalPerTrade: num(bot.quoteNotionalPerTrade),
    minimumConfidence: num(bot.minimumConfidence),
    maxHoldingPeriods: num(bot.maxHoldingPeriods),
    cadenceSeconds: num(bot.cadenceSeconds),
    maxOrderNotional: num(bot.maxOrderNotional),
    maxPositionNotional: num(bot.maxPositionNotional),
    maxDailyLoss: num(bot.maxDailyLoss),
    maxDrawdown: num(bot.maxDrawdown),
    maxConcurrentPositions: num(bot.maxConcurrentPositions),
    maxOrdersPerDay: num(bot.maxOrdersPerDay),
    maxConsecutiveFailures: num(bot.maxConsecutiveFailures),
    maxSlippageBps: num(bot.maxSlippageBps),
    expectedModelVersion: bot.expectedModelVersion ?? '',
    exchangeConnectionId: bot.exchangeConnectionId ?? '',
  }
}

export function BotFormModal({
  isOpen,
  onClose,
  onSaved,
  bot,
}: {
  isOpen: boolean
  onClose: () => void
  /** Called after a successful create *or* update, so the caller refetches once for both. */
  onSaved: () => void
  /** `undefined` creates; present means edit, which locks the market identity fields. */
  bot?: BotDetail | null
}) {
  const isEdit = !!bot

  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [isLoading, setIsLoading] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)
  // The operator's stored connections, offered as the optional credential pin. Fetched once on open;
  // an empty list just means the environment credentials remain the only source.
  const [connections, setConnections] = useState<ExchangeConnection[]>([])

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    api.exchangeConnections
      .list()
      .then(result => {
        if (!cancelled) setConnections((result.items ?? []).filter(c => c.isActive))
      })
      .catch(() => {
        /* a failed listing must not block the form; env credentials still work */
      })
    return () => {
      cancelled = true
    }
  }, [isOpen])

  // The dialog unmounts its body when closed, so seeding from `bot` on open — not on mount — is what
  // makes editing a second bot show the second bot's values.
  useEffect(() => {
    if (!isOpen) return
    setForm(bot ? fromDetail(bot) : EMPTY_FORM)
    setValidationError(null)
  }, [isOpen, bot])

  const set = useCallback(
    <K extends keyof FormState>(key: K, value: FormState[K]) =>
      setForm(current => ({ ...current, [key]: value })),
    [],
  )

  const submit = useCallback(async () => {
    if (!form.name.trim()) {
      setValidationError(fa.validation.botNameRequired)
      return
    }
    if (!isEdit && !form.symbol.trim()) {
      setValidationError(fa.validation.botSymbolRequired)
      return
    }
    for (const key of POSITIVE_NUMBERS) {
      const raw: string = form[key]
      if (raw !== '' && !(parseFloat(raw) > 0)) {
        setValidationError(
          key === 'quoteNotionalPerTrade' ? fa.validation.botNotionalPositive : fa.validation.botPercentPositive,
        )
        return
      }
    }

    const payload: BotInput = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      symbol: form.symbol.trim().toUpperCase(),
      interval: form.interval,
      venue: form.venue,
      operatingMode: form.operatingMode,
      takeProfitPercent: parseFloat(form.takeProfitPercent),
      stopLossPercent: parseFloat(form.stopLossPercent),
      allowShort: form.allowShort,
      leverage: parseInt(form.leverage, 10),
      quoteNotionalPerTrade: parseFloat(form.quoteNotionalPerTrade),
      minimumConfidence: form.minimumConfidence === '' ? 0 : parseFloat(form.minimumConfidence),
      maxHoldingPeriods: form.maxHoldingPeriods === '' ? 0 : parseInt(form.maxHoldingPeriods, 10),
      cadenceSeconds: parseInt(form.cadenceSeconds || '60', 10),
      maxOrderNotional: form.maxOrderNotional === '' ? 0 : parseFloat(form.maxOrderNotional),
      maxPositionNotional: form.maxPositionNotional === '' ? 0 : parseFloat(form.maxPositionNotional),
      maxDailyLoss: form.maxDailyLoss === '' ? 0 : parseFloat(form.maxDailyLoss),
      maxDrawdown: form.maxDrawdown === '' ? 0 : parseFloat(form.maxDrawdown),
      maxConcurrentPositions:
        form.maxConcurrentPositions === '' ? 0 : parseInt(form.maxConcurrentPositions, 10),
      maxOrdersPerDay: form.maxOrdersPerDay === '' ? 0 : parseInt(form.maxOrdersPerDay, 10),
      maxConsecutiveFailures:
        form.maxConsecutiveFailures === '' ? 0 : parseInt(form.maxConsecutiveFailures, 10),
      maxSlippageBps: form.maxSlippageBps === '' ? 0 : parseInt(form.maxSlippageBps, 10),
      expectedModelVersion: form.expectedModelVersion.trim() || null,
      exchangeConnectionId: form.exchangeConnectionId === '' ? null : form.exchangeConnectionId,
    }

    setIsLoading(true)
    setValidationError(null)
    try {
      if (isEdit && bot) await api.bots.update(bot.id, payload)
      else await api.bots.create(payload)
      onSaved()
      onClose()
    } catch (cause) {
      setValidationError(errorMessage(cause))
    } finally {
      setIsLoading(false)
    }
  }, [form, isEdit, bot, onClose, onSaved])

  /** One numeric field, with its label/hint pair resolved from the same key. `fa.bots` is a flat
   *  literal whose keys happen to name these fields, so the lookup goes through a local alias typed
   *  as `Record<string, unknown>` — indexing the real const with a computed string is what TS refuses. */
  const numberField = (
    key: NumericFieldKey,
    options: { step?: string; required?: boolean } = {},
  ) => {
    const labels = fa.bots as Record<string, unknown>
    return (
    <Field
      label={String(labels[key])}
      hint={String(labels[`${key}Hint`] ?? '')}
      required={options.required}
    >
      {ids => (
        <Input
          {...ids}
          type="number"
          step={options.step ?? 'any'}
          min="0"
          value={form[key]}
          onChange={e => set(key, e.target.value)}
          disabled={isLoading}
          className="num"
        />
      )}
    </Field>
    )
  }

  const limitFields = [
    'maxOrderNotional',
    'maxPositionNotional',
    'maxDailyLoss',
    'maxDrawdown',
    'maxConcurrentPositions',
    'maxOrdersPerDay',
    'maxConsecutiveFailures',
    'maxSlippageBps',
  ] as const

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEdit ? fa.bots.editTitle : fa.bots.createTitle}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isLoading}>
            {fa.common.cancel}
          </Button>
          <Button onClick={submit} isLoading={isLoading}>
            {fa.common.save}
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        {validationError && <Alert tone="error">{validationError}</Alert>}

        {/* ── Identity ── */}
        <section className="space-y-4">
          <h3 className="micro-label">{fa.bots.sectionIdentity}</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={fa.bots.name} hint={fa.bots.nameHint} required>
              {ids => (
                <Input
                  {...ids}
                  value={form.name}
                  onChange={e => set('name', e.target.value)}
                  disabled={isLoading}
                />
              )}
            </Field>
            <Field label={fa.bots.description}>
              {ids => (
                <Input
                  {...ids}
                  value={form.description}
                  onChange={e => set('description', e.target.value)}
                  disabled={isLoading}
                />
              )}
            </Field>
          </div>
        </section>

        {/* ── Market ── */}
        <section className="space-y-4">
          <h3 className="micro-label">{fa.bots.sectionMarket}</h3>

          {isEdit && (
            <Alert tone="info">
              {fa.bots.marketLocked}
            </Alert>
          )}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label={fa.trading.symbol} required>
              {ids => (
                <Input
                  {...ids}
                  value={form.symbol}
                  onChange={e => set('symbol', e.target.value.toUpperCase())}
                  placeholder="BTCUSDT"
                  disabled={isEdit || isLoading}
                  className="latin"
                />
              )}
            </Field>

            <Field label={fa.trading.interval} required>
              {ids => (
                <Select
                  {...ids}
                  value={form.interval}
                  onChange={e => set('interval', e.target.value)}
                  disabled={isEdit || isLoading}
                >
                  {INTERVALS.map(i => (
                    <option key={i} value={i}>
                      {i}
                    </option>
                  ))}
                </Select>
              )}
            </Field>

            <Field label={fa.trading.venueLabel}>
              {ids => (
                <Select
                  {...ids}
                  value={form.venue}
                  onChange={e => set('venue', e.target.value as MarketVenueName)}
                  disabled={isEdit || isLoading}
                >
                  {VENUES.map(v => (
                    <option key={v} value={v}>
                      {fa.trading.venue[v] ?? v}
                    </option>
                  ))}
                </Select>
              )}
            </Field>

            <Field label={fa.trading.modeLabel}>
              {ids => (
                <Select
                  {...ids}
                  value={form.operatingMode}
                  onChange={e => set('operatingMode', e.target.value as OperatingModeName)}
                  disabled={isEdit || isLoading}
                >
                  {MODES.map(m => (
                    <option key={m} value={m}>
                      {fa.trading.mode[m] ?? m}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
        </section>

        {/* ── Strategy ── */}
        <section className="space-y-4">
          <h3 className="micro-label">{fa.bots.sectionStrategy}</h3>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {numberField('takeProfitPercent', { required: true, step: '0.1' })}
            {numberField('stopLossPercent', { required: true, step: '0.1' })}
            {numberField('leverage', { step: '1' })}
            {numberField('quoteNotionalPerTrade', { required: true })}
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {numberField('minimumConfidence', { step: '0.01' })}
            {numberField('maxHoldingPeriods', { step: '1' })}
            {numberField('cadenceSeconds', { step: '1' })}
            <Field label={fa.bots.expectedModelVersion} hint={fa.bots.expectedModelVersionHint}>
              {ids => (
                <Input
                  {...ids}
                  value={form.expectedModelVersion}
                  onChange={e => set('expectedModelVersion', e.target.value)}
                  disabled={isLoading}
                  className="latin"
                />
              )}
            </Field>
          </div>

          <Checkbox
            checked={form.allowShort}
            onChange={checked => set('allowShort', checked)}
            label={fa.trading.allowShort}
            description={fa.signal.allowShortHint}
            disabled={isLoading}
          />

          {/* Optional credential pin. Empty = environment credentials; a pinned connection that is
              later deactivated faults the bot rather than silently trading on a revoked key. */}
          {connections.length > 0 && (
            <Field label={fa.connections.pinLabel} hint={fa.connections.pinHint}>
              {ids => (
                <Select
                  {...ids}
                  value={form.exchangeConnectionId}
                  onChange={e => set('exchangeConnectionId', e.target.value)}
                  disabled={isLoading}
                >
                  <option value="">{fa.connections.pinNone}</option>
                  {connections.map(c => (
                    <option key={c.id} value={c.id}>
                      {(fa.trading.venue[c.venue] ?? c.venue) + ' — ' + c.label + ' (****' + c.keyPreview + ')'}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          )}
        </section>

        {/* ── Risk limits ── */}
        <section className="space-y-4">
          <h3 className="micro-label">{fa.bots.sectionLimits}</h3>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {limitFields.map(key => numberField(key))}
          </div>

          {/* The inversion stated where the operator sets the numbers. */}
          <Alert tone="warn">
            {fa.bots.limitsNote}
          </Alert>
        </section>
      </div>
    </Modal>
  )
}
