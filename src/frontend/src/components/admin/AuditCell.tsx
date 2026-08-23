import { ABSENT, auditActor, hasValue, jalaliDate } from '../../lib/format'

/**
 * The "created" column: Jalali date on the first line, who did it on the second.
 *
 * Both values live in the same `creationDate` string — the server interpolates `$"{date} {actor}"` —
 * but `userCreatedName` also arrives on its own, and reading it is better than parsing when it is
 * there. So the actor is taken from the dedicated field and only falls back to splitting the
 * concatenated one, which is what the nested projections leave filled.
 *
 * A row that has never been updated sends `" "` for the modification pair rather than null, so
 * `hasValue` (whitespace-aware) is what decides whether there is a second line at all. Rendering the
 * dash there would claim the actor is unknown; omitting the line says nothing, which is accurate.
 */
export function AuditCell({
  date,
  actor,
}: {
  date: string | null | undefined
  actor: string | null | undefined
}) {
  const day = jalaliDate(date)
  const who = hasValue(actor) ? actor : auditActor(date)

  return (
    <div className="leading-tight">
      <span className="num text-ink-soft">{day}</span>
      {who !== ABSENT && <span className="mt-1 block text-xs text-ink-muted">{who}</span>}
    </div>
  )
}
