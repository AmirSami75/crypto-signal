import { useCallback, useEffect, useState } from 'react'

/**
 * Light/dark, stored per browser.
 *
 * The theme lives on `<html data-theme>` and nowhere else — no context, no provider, no re-render of
 * the tree. Every component reads its colours from custom properties that the attribute swaps
 * underneath them, so a toggle costs one attribute write and a repaint. The only React state here is
 * what the toggle button needs to draw the right icon.
 *
 * The initial read is done in an inline script in `index.html`, before the first paint; see the
 * comment there. This hook picks up whatever that script decided rather than deciding again, which is
 * why `readTheme` looks at the DOM and not at storage.
 */

export type Theme = 'light' | 'dark'

/** Shared with the bootstrap script in index.html. Changing it here means changing it there. */
export const THEME_STORAGE_KEY = 'cs.theme'

const THEME_COLORS: Record<Theme, string> = { light: '#ffffff', dark: '#17191c' }

function readTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

function applyTheme(theme: Theme): void {
  const root = document.documentElement

  // The palette is a plain CSS swap, so it lands instantly and looks like a snap. A short transition
  // class softens it; it is removed again because leaving a global colour transition on makes every
  // subsequent hover feel like it is lagging.
  root.classList.add('theme-transition')
  window.setTimeout(() => root.classList.remove('theme-transition'), 220)

  if (theme === 'dark') root.dataset.theme = 'dark'
  else root.dataset.theme = 'light'

  // The browser chrome — address bar on mobile, title bar in a PWA window — is painted from this and
  // would otherwise stay white behind a dark page.
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLORS[theme])

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // Blocked storage costs the user persistence, not the toggle.
  }
}

export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(readTheme)

  // Two tabs open, one toggles: the other should follow rather than sit on a stale palette. `storage`
  // fires only in the *other* tabs, so this cannot loop with the write in `applyTheme`.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY) return
      const next: Theme = event.newValue === 'dark' ? 'dark' : 'light'
      document.documentElement.dataset.theme = next
      document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLORS[next])
      setTheme(next)
    }

    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === 'dark' ? 'light' : 'dark'
      applyTheme(next)
      return next
    })
  }, [])

  return { theme, toggle }
}
