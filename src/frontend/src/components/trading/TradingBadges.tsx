import { Badge, StatusDot } from '../ui/Badge'
import { fa } from '../../i18n/fa'
import type {
  BotDecisionActionName,
  BotStatusName,
  ExchangeOrderStatusName,
  KillSwitchScopeName,
  OperatingModeName,
  OrderIntentStatusName,
  PositionStatusName,
  TradeDirectionName,
} from '../../lib/apiTypes'

/**
 * The pills that carry the trading vocabulary.
 *
 * One component per enum rather than a generic `<EnumBadge map={…} tone={…}>`, because the *tone* is
 * the part that matters and it is a judgement per value, not a lookup. `Faulted` is danger, `Paused` is
 * warn, `Draft` is neutral — a generic component would push that decision back to every call site and
 * they would drift.
 *
 * Every label goes through a `Record<string, string>` lookup with the raw wire value as its fallback,
 * so an enum member the server adds tomorrow renders as `Reconciling` rather than as `undefined`.
 */

function label(map: Record<string, string>, value: string): string {
  return map[value] ?? value
}

/** `PAPER` / `paper` / `Paper` → `Paper`. Anything unrecognised is returned untouched. */
export function normalizeMode(mode: string): string {
  if (mode.length === 0) return mode
  return mode[0].toUpperCase() + mode.slice(1).toLowerCase()
}

/**
 * The operating mode, and the most important pill in the interface.
 *
 * It appears on every bot screen and inside every start/stop dialog, because the whole safety story
 * rests on the operator never being in doubt about which venue a click reaches. The tones encode that:
 * PAPER is neutral because nothing leaves the process, SANDBOX is accent because orders reach a real
 * venue's test network, and LIVE is danger because real money moves.
 *
 * `emphasis` draws the LIVE case as a filled pill rather than a tinted one. It is unreachable today —
 * `AllowLiveExecution` is false and gates 6-8 of the safety policy are not implemented — and it is
 * written anyway, so that the day it becomes reachable is not also the day someone has to design the
 * warning.
 */
export function OperatingModeBadge({
  mode,
  emphasis = false,
}: {
  mode: OperatingModeName | string
  emphasis?: boolean
}) {
  // `GET /api/v1/platform` sends `PAPER` while a bot record sends `Paper` — the first is a hand-written
  // string in the platform DTO, the second is a serialised enum. Normalising here rather than at three
  // call sites keeps the difference from becoming a rendering bug on whichever screen forgets.
  const canonical = normalizeMode(mode)
  const text = label(fa.trading.mode, canonical)
  const tone = canonical === 'Live' ? 'danger' : canonical === 'Sandbox' ? 'accent' : 'neutral'

  return (
    <Badge tone={tone} className={emphasis && canonical === 'Live' ? 'font-semibold' : ''}>
      <StatusDot tone={tone} />
      <span>{`${fa.trading.modeLabel}: ${text}`}</span>
    </Badge>
  )
}

/** Bot lifecycle. `Faulted` is the one an operator has to notice, so it is the only danger tone. */
export function BotStatusBadge({ status }: { status: BotStatusName | string }) {
  const tone =
    status === 'Active'
      ? 'success'
      : status === 'Faulted'
        ? 'danger'
        : status === 'Paused'
          ? 'warn'
          : 'neutral'

  return (
    <Badge tone={tone}>
      <StatusDot tone={tone} pulse={status === 'Active'} />
      <span>{label(fa.trading.botStatus, status)}</span>
    </Badge>
  )
}

/**
 * Which way a bet points.
 *
 * Green for long and red for short is the convention everywhere a price is drawn, so it is what a
 * reader's eye is already trained on — but the word is present too. Colour alone would leave the
 * direction unreadable to anyone who cannot distinguish the two hues, and this is the field where
 * getting it wrong is most expensive.
 */
export function DirectionBadge({ direction }: { direction: TradeDirectionName | string }) {
  const tone = direction === 'Long' ? 'success' : direction === 'Short' ? 'danger' : 'neutral'
  return <Badge tone={tone}>{label(fa.trading.direction, direction)}</Badge>
}

/** What the engine advised. `Close` is warn rather than danger: closing is the safe half of trading. */
export function ActionBadge({ action }: { action: BotDecisionActionName | string }) {
  const tone =
    action === 'Open' ? 'accent' : action === 'Close' ? 'warn' : action === 'AdjustBracket' ? 'accent' : 'neutral'
  return <Badge tone={tone}>{label(fa.trading.action, action)}</Badge>
}

export function PositionStatusBadge({ status }: { status: PositionStatusName | string }) {
  const tone = status === 'Open' ? 'accent' : 'neutral'
  return <Badge tone={tone}>{label(fa.trading.positionStatus, status)}</Badge>
}

/**
 * An intent's status, including the two refusals.
 *
 * `RiskDenied` and `Rejected` are both danger tones and they mean different things: the first is the
 * platform refusing to send an order, the second is the venue refusing to accept one. Both are
 * outcomes worth recording — a refusal is evidence, not an error to be discarded.
 */
export function IntentStatusBadge({ status }: { status: OrderIntentStatusName | string }) {
  const tone =
    status === 'Filled'
      ? 'success'
      : status === 'RiskDenied' || status === 'Rejected'
        ? 'danger'
        : status === 'Ambiguous'
          ? 'warn'
          : status === 'PartiallyFilled' || status === 'Submitted' || status === 'Submitting'
            ? 'accent'
            : 'neutral'

  return <Badge tone={tone}>{label(fa.trading.intentStatus, status)}</Badge>
}

/** A venue order's status. `Unknown` is warn — an unreconciled order is a state to act on. */
export function OrderStatusBadge({ status }: { status: ExchangeOrderStatusName | string }) {
  const tone =
    status === 'Filled'
      ? 'success'
      : status === 'Rejected'
        ? 'danger'
        : status === 'Unknown' || status === 'PendingCancel'
          ? 'warn'
          : status === 'PartiallyFilled' || status === 'New'
            ? 'accent'
            : 'neutral'

  return <Badge tone={tone}>{label(fa.trading.orderStatus, status)}</Badge>
}

/**
 * A kill switch's scope and state in one pill.
 *
 * Engaged is danger, which inverts the usual reading — a red pill here means the platform is refusing
 * to trade, which is the *safe* state. The alternative is worse: painting an engaged switch green
 * because "safety is good" would make the one screen an operator reaches for in a hurry say the
 * opposite of what every other screen's red means.
 */
export function KillSwitchStateBadge({ isEngaged }: { isEngaged: boolean }) {
  return (
    <Badge tone={isEngaged ? 'danger' : 'neutral'}>
      <StatusDot tone={isEngaged ? 'danger' : 'neutral'} pulse={isEngaged} />
      <span>{isEngaged ? fa.killSwitches.stateEngaged : fa.killSwitches.stateDisengaged}</span>
    </Badge>
  )
}

export function scopeLabel(scope: KillSwitchScopeName | string): string {
  return label(fa.trading.killSwitchScope, scope)
}

/** The engine's `reason_code` in words, falling back to the raw token. */
export function reasonCodeLabel(code: string | null | undefined): string {
  if (!code) return ''
  return fa.trading.reasonCode[code] ?? code
}

/** A `RiskCheck` member name in words, falling back to the English name the server sent. */
export function riskCheckLabel(check: string): string {
  return fa.trading.riskCheck[check] ?? check
}

/** A venue in words. */
export function venueLabel(venue: string): string {
  return label(fa.trading.venue, venue)
}

/** A `BotAuditEventType` in words. */
export function auditEventLabel(eventType: string): string {
  return label(fa.trading.auditEvent, eventType)
}

/** A `PositionCloseReason` in words, or the dash when a position is still open. */
export function closeReasonLabel(reason: string | null | undefined): string | null {
  if (!reason) return null
  return fa.trading.closeReason[reason] ?? reason
}
