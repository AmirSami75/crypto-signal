import { ABSENT } from './format'

/**
 * Numbers and timestamps for the trading screens.
 *
 * Separate from `format.ts`, which exists to undo specific quirks of the *auth* wire format — a date
 * with an actor's name glued to it, a modification field that is a lone space. Nothing here is
 * undoing a quirk. The trading endpoints send clean ISO-8601 instants and JSON numbers; the work is
 * turning them into something a Persian-reading operator can compare at a glance without being lied
 * to about precision.
 *
 * Three rules run through all of it.
 *
 * **Latin digits, always.** Every formatter asks for `en-US` numerals or the `-nu-latn` extension. A
 * price is compared against an exchange screen and a chart, and both of those show `43,218.50`.
 *
 * **Never invent precision, never hide it.** A price is formatted by magnitude, so `43218.5` keeps two
 * decimals and `0.00004312` keeps eight — a fixed two-decimal format would render an altcoin's price
 * as `0.00`, and a fixed eight would turn a bitcoin price into a wall of zeros.
 *
 * **These values are read, not summed.** The server computes every total in `decimal` and sends the
 * result; nothing here adds two numbers together, so the `double` these arrive as costs nothing. The
 * moment a screen wants a derived total, it belongs on the server instead.
 */

/**
 * Jalali date and 24-hour time from an ISO instant, in the reader's own timezone.
 *
 * Local time, not UTC, and deliberately: the operator's question is "how long ago was that", which is
 * answered in the clock on their wall. The server records UTC and the audit chain is UTC throughout —
 * the conversion is a presentation step and happens nowhere else.
 */
const DATE_TIME = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

const TIME_ONLY = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

/** `1405/05/27, 13:00`, or the dash when the field is absent or unparseable. */
export function dateTimeText(iso: string | null | undefined): string {
  const date = toDate(iso)
  return date ? DATE_TIME.format(date) : ABSENT
}

/** `13:00:42` — for a column where the date is already established by its neighbours. */
export function timeText(iso: string | null | undefined): string {
  const date = toDate(iso)
  return date ? TIME_ONLY.format(date) : ABSENT
}

/**
 * Whole seconds between now and an instant, negative once it has passed.
 *
 * Returns `null` for an absent or unparseable value so a caller can distinguish "no deadline" from
 * "the deadline is now", which are different things for a signal's validity.
 */
export function secondsUntil(iso: string | null | undefined, now: number = Date.now()): number | null {
  const date = toDate(iso)
  if (!date) return null
  return Math.round((date.getTime() - now) / 1000)
}

/** `04:37` from a count of seconds — a countdown, so it clamps at zero rather than going negative. */
export function countdownText(seconds: number): string {
  const clamped = Math.max(0, seconds)
  const minutes = Math.floor(clamped / 60)
  const rest = clamped % 60

  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60)
    return `${pad(hours)}:${pad(minutes % 60)}:${pad(rest)}`
  }

  return `${pad(minutes)}:${pad(rest)}`
}

/**
 * A price, with decimals chosen by magnitude.
 *
 * The thresholds are not arbitrary — they are what keeps the same column readable for a $43,000 pair
 * and a $0.000043 one. Grouping separators stay on, because four digits of a price without them is
 * where a misread order size comes from.
 */
export function priceText(value: number | null | undefined): string {
  if (!isFinite(value)) return ABSENT

  const magnitude = Math.abs(value)
  const digits = magnitude === 0 ? 2 : magnitude >= 1000 ? 2 : magnitude >= 1 ? 4 : magnitude >= 0.01 ? 6 : 8

  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: digits,
  }).format(value)
}

/** A quantity: up to eight decimals, trailing zeros dropped. Binance step sizes go that deep. */
export function quantityText(value: number | null | undefined): string {
  if (!isFinite(value)) return ABSENT
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 8 }).format(value)
}

/** A quote-currency amount, always two decimals — this is the column an operator sums by eye. */
export function moneyText(value: number | null | undefined): string {
  if (!isFinite(value)) return ABSENT
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
}

/**
 * A P&L figure with an explicit sign.
 *
 * `+` on a profit is not decoration: `12.40` and `-12.40` differ by one character at the *start* of an
 * LTR-isolated run inside RTL prose, which is the easiest place in this whole interface to misread.
 */
export function signedMoneyText(value: number | null | undefined): string {
  if (!isFinite(value)) return ABSENT
  const formatted = moneyText(Math.abs(value))
  if (value > 0) return `+${formatted}`
  if (value < 0) return `-${formatted}`
  return formatted
}

/** A percentage that arrives already denominated in percent (`2.5` → `2.5%`). */
export function percentText(value: number | null | undefined, digits = 2): string {
  if (!isFinite(value)) return ABSENT
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value)}%`
}

/** A probability that arrives as a 0..1 share (`0.6231` → `62.3%`). */
export function shareText(value: number | null | undefined, digits = 1): string {
  if (!isFinite(value)) return ABSENT
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value * 100)}%`
}

/** A plain count. */
export function countText(value: number | null | undefined): string {
  if (!isFinite(value)) return ABSENT
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)
}

/** A dimensionless ratio — an R:R, an ATR multiple, an expected value. */
export function ratioText(value: number | null | undefined, digits = 2): string {
  if (!isFinite(value)) return ABSENT
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}

/**
 * The first and last few characters of a hash, joined by an ellipsis.
 *
 * A digest is there so two runs can be compared, and the ends are what a person compares. Printing all
 * 64 characters in a table cell sets the column width for every other row and gets read by nobody.
 */
export function digestText(value: string | null | undefined, edge = 8): string {
  if (typeof value !== 'string' || value.trim().length === 0) return ABSENT
  const trimmed = value.trim()
  return trimmed.length <= edge * 2 + 1 ? trimmed : `${trimmed.slice(0, edge)}…${trimmed.slice(-edge)}`
}

/** A duration in seconds as Persian prose: `۹۰ ثانیه` → `1 دقیقه و 30 ثانیه`, in Latin digits. */
export function cadenceText(seconds: number | null | undefined): string {
  if (!isFinite(seconds) || (seconds as number) <= 0) return ABSENT

  const total = Math.round(seconds as number)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const rest = total % 60

  const parts: string[] = []
  if (hours > 0) parts.push(`${countText(hours)} ساعت`)
  if (minutes > 0) parts.push(`${countText(minutes)} دقیقه`)
  if (rest > 0) parts.push(`${countText(rest)} ثانیه`)

  return parts.join(' و ')
}

function isFinite(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function pad(value: number): string {
  return value.toString().padStart(2, '0')
}

function toDate(iso: string | null | undefined): Date | null {
  if (typeof iso !== 'string' || iso.trim().length === 0) return null
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date
}
