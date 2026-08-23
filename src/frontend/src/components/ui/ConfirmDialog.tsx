import { useState, type ReactNode } from 'react'
import { fa } from '../../i18n/fa'
import { Alert } from './Alert'
import { Button } from './Button'
import { Modal } from './Modal'

/**
 * Confirmation for an action that is awkward or impossible to undo.
 *
 * It owns the request rather than just reporting a decision: `onConfirm` is awaited, the button shows
 * its own pending state, and a failure is rendered *inside* the dialog instead of closing it. That
 * last part is the reason this is a component and not two lines of `window.confirm`.
 *
 * The server refuses several of these outright — deactivating `cs-admin`, deleting a seeded role — and
 * it refuses them with a specific Persian sentence explaining which rule was hit. Closing on submit
 * and surfacing that sentence as a toast somewhere else would strand the explanation away from the
 * thing it explains. Keeping the dialog open puts the refusal where the user is already looking, with
 * the action still in front of them.
 */
export function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  body,
  confirmLabel,
  /** `danger` for anything destructive; `primary` for a state change that can be undone. */
  tone = 'danger',
}: {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => Promise<void>
  title: string
  body: ReactNode
  confirmLabel: string
  tone?: 'danger' | 'primary'
}) {
  const [isPending, setIsPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dismiss = () => {
    if (isPending) return
    setError(null)
    onClose()
  }

  const confirm = async () => {
    setIsPending(true)
    setError(null)
    try {
      await onConfirm()
      // The parent closes on success — it also has to refetch, and doing both here would make the
      // order of those two things this component's business.
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : fa.errors.unexpected)
    } finally {
      setIsPending(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={dismiss}
      title={title}
      footer={
        <>
          <Button variant="outline" onClick={dismiss} disabled={isPending}>
            {fa.common.cancel}
          </Button>
          <Button variant={tone} onClick={confirm} isLoading={isPending}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="text-sm leading-relaxed text-ink-soft">{body}</div>
        {error && <Alert tone="error">{error}</Alert>}
      </div>
    </Modal>
  )
}
