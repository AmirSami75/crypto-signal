import { useEffect, useState } from 'react'
import { api } from './api'
import type { PlatformInfo, Readiness } from './apiTypes'

/**
 * The two anonymous status endpoints, as hooks.
 *
 * Split into two rather than one that fetches both: the login screen needs only the operating mode,
 * and `/health/ready` reaches through to PostgreSQL and the Python ML service on every call. Making
 * an unauthenticated page poll a dependency health check it does not display would put avoidable
 * load on both, for nothing shown.
 *
 * Both abort on unmount, so a navigation away mid-flight does not set state on a gone component.
 */

type Result<T> = { data: T | null; error: boolean; isLoading: boolean }

function useAnonymousResource<T>(fetcher: (signal: AbortSignal) => Promise<T>): Result<T> {
  const [state, setState] = useState<Result<T>>({ data: null, error: false, isLoading: true })

  useEffect(() => {
    const controller = new AbortController()

    fetcher(controller.signal)
      .then((data) => setState({ data, error: false, isLoading: false }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setState({ data: null, error: true, isLoading: false })
      })

    return () => controller.abort()
    // The fetcher is a stable module-level function; re-running on identity change would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return state
}

/** `GET /api/v1/platform` — operating mode and the execution-policy sentence. */
export function usePlatform() {
  return useAnonymousResource<PlatformInfo>((signal) => api.platform.info(signal))
}

/** `GET /health/ready` — aggregate readiness, including PostgreSQL and the Python ML service. */
export function useReadiness() {
  return useAnonymousResource<Readiness>((signal) => api.platform.readiness(signal))
}
