import { fa } from '../i18n/fa'

/**
 * Live mirror of the server's `IsStrongPassword`
 * (`Infra/Extensions/Type/StringExtensions.cs`), which requires **all five** conditions.
 *
 * The mirror is deliberately exact, because a client check that disagrees with the server is worse
 * than none: too strict and it refuses a password the server would have taken, too loose and it
 * promises one the server will reject.
 *
 * Two details are easy to get wrong:
 *
 * 1. **The special-character set is a closed list of 21**, not "any punctuation". Absent from it:
 *    `^ [ ] { } ; : ' " \` and the backtick. A password whose only special character is `^` fails
 *    server-side, so it has to fail here too.
 * 2. **The case and digit tests are Unicode-aware on the server.** `char.IsLower`, `char.IsUpper` and
 *    `char.IsDigit` test Unicode categories, so a Persian digit like `۵` genuinely satisfies the
 *    digit rule. JavaScript's `\d` is only `[0-9]`, which would have been stricter than the server
 *    and would have marked such a password invalid — hence `\p{Nd}`, `\p{Ll}` and `\p{Lu}`, which
 *    match the same categories .NET checks.
 *
 * Length is compared the same way on both sides: .NET's `string.Length` and JavaScript's
 * `String.length` both count UTF-16 code units.
 */

export const SPECIAL_CHARACTERS = '!%$#@&*()-_+=~|,<.>?/'

const SPECIAL_SET = new Set(SPECIAL_CHARACTERS)

// `u` flag required for \p{…} escapes.
const HAS_LOWER = /\p{Ll}/u
const HAS_UPPER = /\p{Lu}/u
const HAS_DIGIT = /\p{Nd}/u

export type PasswordCheck = {
  length: boolean
  lower: boolean
  upper: boolean
  digit: boolean
  special: boolean
}

export function checkPassword(password: string): PasswordCheck {
  return {
    length: password.length >= 8,
    lower: HAS_LOWER.test(password),
    upper: HAS_UPPER.test(password),
    digit: HAS_DIGIT.test(password),
    special: [...password].some((character) => SPECIAL_SET.has(character)),
  }
}

export function isPasswordStrong(password: string): boolean {
  return Object.values(checkPassword(password)).every(Boolean)
}

type PasswordRulesProps = {
  password: string
  /** Adds a sixth row for the confirmation field, when there is one. */
  confirmPassword?: string
  className?: string
}

export function PasswordRules({ password, confirmPassword, className = '' }: PasswordRulesProps) {
  const checks = checkPassword(password)

  const rows: Array<{ key: string; label: string; met: boolean; suffix?: string }> = [
    { key: 'length', label: fa.passwordRules.length, met: checks.length },
    { key: 'lower', label: fa.passwordRules.lower, met: checks.lower },
    { key: 'upper', label: fa.passwordRules.upper, met: checks.upper },
    { key: 'digit', label: fa.passwordRules.digit, met: checks.digit },
    // The set is shown rather than described, so nobody has to guess whether their `^` counts.
    { key: 'special', label: fa.passwordRules.special, met: checks.special, suffix: SPECIAL_CHARACTERS },
  ]

  if (confirmPassword !== undefined) {
    rows.push({
      key: 'match',
      label: fa.passwordRules.match,
      met: password.length > 0 && password === confirmPassword,
    })
  }

  return (
    <div className={`rounded-xl border border-line bg-surface-muted p-3.5 ${className}`}>
      <p className="micro-label">{fa.passwordRules.title}</p>

      {/*
        aria-live="polite" so the list is announced as it changes, but the whole group is one live
        region — announcing five separate rows on every keystroke would be unusable.
      */}
      <ul className="mt-2.5 space-y-1.5" aria-live="polite">
        {rows.map((row) => (
          <li key={row.key} className="flex items-start gap-2 text-xs">
            <RuleIcon met={row.met} />
            <span className={row.met ? 'text-ink-soft' : 'text-ink-muted'}>
              {row.label}
              {row.suffix && (
                <>
                  {' '}
                  <span className="num rounded-md border border-line bg-surface px-1.5 py-0.5 tracking-wider text-ink-soft">
                    {row.suffix}
                  </span>
                </>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function RuleIcon({ met }: { met: boolean }) {
  return (
    <span
      // The icon is decorative: the colour change plus the live region already convey state, and a
      // screen reader reading "check mark" before each of six rows is noise.
      aria-hidden="true"
      className={`mt-0.5 grid size-3.5 shrink-0 place-items-center rounded-full border ${
        met ? 'border-success bg-success/15 text-success-ink' : 'border-line-strong text-transparent'
      }`}
    >
      <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.2" className="size-2.5">
        <path d="M2.5 6.3l2.2 2.2L9.5 3.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  )
}
