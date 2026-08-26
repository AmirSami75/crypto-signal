import { useEffect, useRef } from 'react'

/**
 * Runs `fn` on an interval while the component is mounted.
 *
 * Built for monitoring screens: `fn` is re-read through a ref each tick, so the callback can close
 * over fresh state without the interval being torn down and recreated on every render — a plain
 * `useEffect(() => { setInterval(fn, ms) }, [fn])` resets the timer whenever any captured value
 * changes, which on a polling screen is constantly.
 *
 * `enabled=false` stops scheduling entirely (used when a bot is not in a state worth polling).
 */
export function useInterval(fn: () => void, milliseconds: number, enabled = true): void {
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!enabled) return
    const timer = window.setInterval(() => fnRef.current(), milliseconds)
    return () => window.clearInterval(timer)
  }, [milliseconds, enabled])
}
