import { useCallback, useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { fa } from '../../i18n/fa'
import { IconButton } from './IconButton'

/**
 * A modal dialog: scrim, centred panel, and the four behaviours a dialog is expected to have.
 *
 * There is no `<dialog>` element here, and that is a considered choice rather than an oversight.
 * `showModal()` brings a real top layer and a free `::backdrop`, but it also brings its own focus
 * management that fights a React-controlled `isOpen` prop, and its backdrop cannot be transitioned or
 * tinted from a custom property in every browser this has to run in. What it would save is the focus
 * trap below; what it would cost is control over the parts of this design that are not negotiable.
 *
 * The four behaviours, each of which is a real bug when missing:
 *
 * 1. **Focus moves in and comes back.** Opening focuses the panel; closing returns focus to whatever
 *    opened it. Without the return, dismissing a dialog dumps focus at the top of the document and a
 *    keyboard user has to tab back through the entire sidebar to reach the button they just pressed.
 * 2. **Tab is trapped.** Otherwise Tab walks out of the dialog into the page behind it, which is
 *    inert to the eye but not to the keyboard — a user can type into a form they cannot see.
 * 3. **Escape and the scrim dismiss.** Both are cancellations, so both are routed through `onClose`
 *    and neither one submits.
 * 4. **The page behind does not scroll.** With the panel taller than the viewport on a phone, a
 *    scroll gesture that reaches the body scrolls the wrong thing.
 *
 * The scroll lock compensates for the scrollbar it removes. Hiding the body's overflow reclaims the
 * scrollbar's width, and the whole layout jumps sideways by that much at the moment the dialog opens
 * — a flinch that reads as a rendering fault. Padding the reclaimed width back on holds it still.
 */
export function Modal({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: {
  isOpen: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
  /** Pinned to the bottom of the panel, outside the scrolling body — where the actions belong. */
  footer?: ReactNode
  size?: 'md' | 'lg'
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const restoreFocusRef = useRef<HTMLElement | null>(null)
  const titleId = useId()
  const descriptionId = useId()

  const focusables = useCallback((): HTMLElement[] => {
    const panel = panelRef.current
    if (!panel) return []
    return Array.from(
      panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
      // `offsetParent === null` filters out anything inside a hidden branch; a trap that cycles
      // through invisible elements strands the focus ring where nothing appears to be selected.
    ).filter((element) => element.offsetParent !== null)
  }, [])

  useEffect(() => {
    if (!isOpen) return

    restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null

    // The panel itself, not the first field. Focusing a text input immediately pops the keyboard on a
    // phone over the dialog's own title, and a screen reader reads the field's label instead of what
    // the dialog is for. `tabIndex={-1}` on the panel is what makes it focusable at all.
    panelRef.current?.focus()

    const { body, documentElement } = document
    const previousOverflow = body.style.overflow
    const previousPadding = body.style.paddingInlineEnd
    const scrollbar = window.innerWidth - documentElement.clientWidth
    body.style.overflow = 'hidden'
    if (scrollbar > 0) body.style.paddingInlineEnd = `${scrollbar}px`

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab') return

      const items = focusables()
      if (items.length === 0) {
        // Nothing to move to, so Tab would leave the dialog. Swallow it.
        event.preventDefault()
        return
      }

      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement

      // The `!panel.contains(active)` arm covers focus having escaped already — after a click on the
      // scrim, or a focused element being removed from the DOM by a re-render.
      if (event.shiftKey && (active === first || !panelRef.current?.contains(active))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (active === last || !panelRef.current?.contains(active))) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', onKeyDown, true)

    return () => {
      window.removeEventListener('keydown', onKeyDown, true)
      body.style.overflow = previousOverflow
      body.style.paddingInlineEnd = previousPadding
      restoreFocusRef.current?.focus()
    }
  }, [isOpen, onClose, focusables])

  if (!isOpen) return null

  return createPortal(
    // Above the mobile drawer's z-50 rather than merely equal to it: a dialog opened while the drawer
    // is still mounted must not race it on DOM order.
    <div className="fixed inset-0 z-[60] flex items-end justify-center overflow-y-auto p-0 sm:items-center sm:p-6">
      <div className="fixed inset-0 bg-scrim" onClick={onClose} aria-hidden="true" />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={[
          'relative flex max-h-[92dvh] w-full flex-col bg-surface shadow-float outline-none',
          // Full-bleed sheet on a phone, floating card above it: at 375px a centred card with margins
          // wastes a third of the width a form needs.
          'rounded-t-2xl sm:rounded-2xl',
          'border border-line',
          size === 'lg' ? 'sm:max-w-3xl' : 'sm:max-w-xl',
        ].join(' ')}
      >
        <header className="flex shrink-0 items-start gap-3 border-b border-line px-5 py-4 sm:px-6">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-base font-semibold text-ink">
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className="mt-1 text-xs leading-relaxed text-ink-muted">
                {description}
              </p>
            )}
          </div>

          <IconButton label={fa.common.close} onClick={onClose} className="-me-1.5">
            <CloseIcon />
          </IconButton>
        </header>

        {/* The scroll lives here, so the header and the footer stay put on a long form. */}
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6">{children}</div>

        {footer && (
          <footer className="flex shrink-0 flex-wrap items-center justify-end gap-3 border-t border-line px-5 py-4 sm:px-6">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body,
  )
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="size-4.5" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
    </svg>
  )
}
