import { fa } from '../i18n/fa'
import { useTheme } from '../lib/useTheme'
import { IconButton } from './ui/IconButton'

/**
 * Light/dark switch.
 *
 * The icon shows the theme the button will *switch to*, not the one currently active, and the label
 * says so in words — "switch to dark". A toggle that shows its current state is ambiguous the moment
 * it is the only control on screen, and it is the label, not the glyph, that a screen reader reads.
 */
export function ThemeToggle({ className = '' }: { className?: string }) {
  const { theme, toggle } = useTheme()
  const isDark = theme === 'dark'

  return (
    <IconButton
      label={isDark ? fa.theme.switchToLight : fa.theme.switchToDark}
      onClick={toggle}
      aria-pressed={isDark}
      className={className}
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
    </IconButton>
  )
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="size-4.5" aria-hidden="true">
      <circle cx="12" cy="12" r="4.2" />
      <path
        d="M12 2.8v2.1M12 19.1v2.1M4.6 4.6l1.5 1.5M17.9 17.9l1.5 1.5M2.8 12h2.1M19.1 12h2.1M4.6 19.4l1.5-1.5M17.9 6.1l1.5-1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="size-4.5" aria-hidden="true">
      <path
        d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
