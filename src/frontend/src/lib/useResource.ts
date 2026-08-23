import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from './api'

/**
 * Fetch-with-refetch for the authenticated listings.
 *
 * `usePlatform`'s hook fires once and never again, which is right for a status endpoint and wrong for
 * everything on the admin screens: creating a user, activating an account or changing a page all have
 * to re-read the same URL. So this one differs in three ways that each earn their complexity.
 *
 * **The fetcher is a dependency, and callers must memoise it.** A listing's fetcher closes over the
 * page number and the filters, so it genuinely changes and re-running is the desired behaviour — that
 * is how pagination works here. The cost is that an unmemoised inline arrow is a new function every
 * render and would loop forever. Callers pass a `useCallback`; there is no way to have it both ways.
 *
 * **In-flight requests are aborted on replacement, not just on unmount.** Type into a filter box and
 * five requests leave in a second; without cancellation the one that happens to land last wins, and
 * that is not necessarily the one matching what is on screen. Aborting the previous request makes the
 * newest query the only possible answer.
 *
 * **`isLoading` stays false for a refetch that has data behind it.** A table that empties itself into
 * skeletons on every keystroke is worse than one that dims: the row heights change, the scroll
 * position jumps, and the eye loses its place. `isRefreshing` is the signal for that case.
 */

export type Resource<T> = {
  data: T | null
  error: string | null
  /** First load only — there is nothing on screen yet. */
  isLoading: boolean
  /** A reload while previous data is still displayed. */
  isRefreshing: boolean
  /** Re-runs the current fetcher. Safe to call from an event handler. */
  refetch: () => void
}

export function useResource<T>(fetcher: (signal: AbortSignal) => Promise<T>): Resource<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)

  // Bumped to force a re-run of the effect for the same fetcher, which is what `refetch` is.
  const [nonce, setNonce] = useState(0)
  const controllerRef = useRef<AbortController | null>(null)

  // Read inside the effect so having data or not does not itself re-trigger the effect — reading
  // `data` directly there would make every successful load schedule another one.
  const hasDataRef = useRef(false)

  useEffect(() => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    if (hasDataRef.current) setIsRefreshing(true)
    else setIsLoading(true)

    fetcher(controller.signal)
      .then((next) => {
        if (controller.signal.aborted) return
        hasDataRef.current = true
        setData(next)
        setError(null)
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        if (cause instanceof DOMException && cause.name === 'AbortError') return
        setError(errorMessage(cause))
        // The stale rows are kept deliberately: an error on a refetch should annotate what is on
        // screen, not blank it. A failed *first* load has nothing to keep, so the table falls through
        // to its error state either way.
      })
      .finally(() => {
        if (controller.signal.aborted) return
        setIsLoading(false)
        setIsRefreshing(false)
      })

    return () => controller.abort()
  }, [fetcher, nonce])

  const refetch = useCallback(() => setNonce((current) => current + 1), [])

  return { data, error, isLoading, isRefreshing, refetch }
}
