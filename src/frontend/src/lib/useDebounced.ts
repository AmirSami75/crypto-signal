import { useEffect, useState } from 'react'

/**
 * The value, held back until it has stopped changing for `delay` milliseconds.
 *
 * Used for the filter boxes on the admin listings, where the alternative is a request per keystroke:
 * typing a five-letter username fires five paged queries, four of which are already stale before they
 * land. `useResource` aborts the superseded ones so the wrong answer never wins, but they still cost
 * a round trip each and still make the table flicker five times.
 *
 * The identity of the return value is what callers depend on: it changes only when a new value is
 * committed, so a `useCallback` fetcher that closes over it re-runs once per settled query rather
 * than once per keypress.
 *
 * The first render returns the initial value immediately rather than after a delay — a listing should
 * not wait 350ms to make its first request just because the filter is wired through here.
 */
export function useDebounced<T>(value: T, delay = 350): T {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])

  return settled
}
