/**
 * Converts Persian (U+06F0–U+06F9) and Arabic-Indic (U+0660–U+0669) digits to ASCII.
 *
 * The server's `IsValidPhone` pattern is `^0[0-9]{2,}[0-9]{7,}$` — ASCII digits only. A Persian
 * keyboard produces `۰۹۱۲…` by default, so a user typing their own mobile number the natural way
 * would be told it is invalid. Converting on the way out is the fix; the alternative, showing a
 * Latin-digit placeholder and expecting the user to switch keyboards, pushes the platform's problem
 * onto them.
 *
 * Only digits are touched, so a value that is already ASCII passes through unchanged.
 */
export function toLatinDigits(value: string): string {
  return value.replace(/[۰-۹٠-٩]/g, (digit) => {
    const code = digit.codePointAt(0)!
    const base = code >= 0x06f0 ? 0x06f0 : 0x0660
    return String(code - base)
  })
}
