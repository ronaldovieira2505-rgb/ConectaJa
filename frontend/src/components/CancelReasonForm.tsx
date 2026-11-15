import { useState, type FormEvent } from 'react'
import { Button, Field } from './ui'

/** Pede o motivo (obrigatório) e confirma um cancelamento feito pela empresa (US71). */
export default function CancelReasonForm({
  confirmLabel,
  label = 'Motivo do cancelamento',
  emptyMessage = 'Informe o motivo do cancelamento.',
  onConfirm,
  onBack,
}: {
  confirmLabel: string
  label?: string
  emptyMessage?: string
  onConfirm: (reason: string) => Promise<void> | void
  onBack: () => void
}) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!reason.trim()) {
      setError(emptyMessage)
      return
    }
    setError('')
    setBusy(true)
    try {
      await onConfirm(reason.trim())
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <Field
        label={label}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        aria-invalid={error ? true : undefined}
      />
      {error && (
        <p role="alert" className="erro">
          {error}
        </p>
      )}
      <div className="acoes">
        <Button type="submit" busy={busy}>
          {confirmLabel}
        </Button>
        <Button type="button" variant="secondary" onClick={onBack}>
          Voltar
        </Button>
      </div>
    </form>
  )
}
