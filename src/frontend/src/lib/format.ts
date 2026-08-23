/**
 * Presentation helpers for the awkward parts of the API's wire format.
 *
 * All three exist because a field that *looks* renderable is not: `creationDate` is two values in one
 * string, `modificationDate` is a lone space when absent, and a user agent is a 120-character line
 * that would set a table column's width for every other row.
 */

/** The em dash used wherever a value is genuinely absent, so blank cells never read as a bug. */
export const ABSENT = '—'

/**
 * True when a string carries something a reader would call a value.
 *
 * The whitespace test is the whole point. `BaseOutputDto` builds its modification fields by
 * interpolating two nulls into `$"{date} {actor}"`, which yields `" "` — not null, not empty. A
 * `value ?? ABSENT` check passes that straight through and paints an empty cell that looks like a
 * rendering failure rather than like "never modified".
 */
export function hasValue(value: string | null | undefined): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

/**
 * The Jalali date out of a `"1405/06/01 System Administrator"` audit string.
 *
 * The server joins the date and the acting user's display name with a single space, and that name may
 * itself contain spaces — so the date is the *first* whitespace-delimited token and nothing else can
 * be assumed about the rest. Splitting on the first space rather than the last is what keeps
 * `"System Administrator"` from contributing `"Administrator"` to the date.
 *
 * Digits arrive as ASCII already; the server's Jalali converter does not emit Persian numerals, so
 * there is nothing to transliterate on the way in.
 */
export function jalaliDate(value: string | null | undefined): string {
  if (!hasValue(value)) return ABSENT
  return value.trim().split(/\s+/)[0]
}

/**
 * The acting user out of the same string, for the cases where `userCreatedName` is not to hand.
 *
 * Prefer the dedicated `userCreatedName` / `userLastUpdateName` fields where they exist — they are
 * the same value without the parsing. This is for nested DTOs whose projection fills the concatenated
 * field but not the separate one.
 */
export function auditActor(value: string | null | undefined): string {
  if (!hasValue(value)) return ABSENT
  const rest = value.trim().split(/\s+/).slice(1).join(' ')
  return rest || ABSENT
}

/**
 * The client column of the login-history table.
 *
 * The stored value is not a user-agent string, despite the field's name: `AddLoginHistory` builds it
 * as `$"{clientOsName} {clientBrowserName}".Trim()` from the two `X-Client*` headers the dashboard
 * sends, so it arrives as `"Linux Chrome"` — already two short tokens. There is nothing to parse.
 *
 * What there *is* to do is handle the three degenerate values the field genuinely takes: `""` for a
 * sign-in that sent no hints at all (a curl call, or anything that is not this dashboard), and
 * `"Unknown"` in either position when the client sent a hint it could not determine. Printing
 * `"Unknown Unknown"` in a table cell is worse than printing nothing, so both collapse to the dash.
 */
export function describeClient(userAgent: string | null | undefined): string {
  if (!hasValue(userAgent)) return ABSENT

  const known = userAgent
    .trim()
    .split(/\s+/)
    .filter((token) => token.toLowerCase() !== 'unknown')

  return known.length > 0 ? known.join(' · ') : ABSENT
}

/**
 * The 1-based row range a page covers, as `[from, to]`.
 *
 * Computed from the grand total rather than from the page's own item count, so the last page reports
 * its real extent instead of a full page's worth.
 */
export function pageRange(page: number, pageSize: number, totalRecords: number): [number, number] {
  if (totalRecords === 0) return [0, 0]
  const from = (page - 1) * pageSize + 1
  return [from, Math.min(page * pageSize, totalRecords)]
}
