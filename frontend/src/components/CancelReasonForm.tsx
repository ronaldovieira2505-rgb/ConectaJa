import { useState, type FormEvent } from 'react'
import { Button, Field } from './ui'

/** Pede o motivo (obrigatório) e confirma um cancelamento feito pela empresa (US71). */
export default function CancelReasonForm({
  confirmLabel,
  onConfirm,
  onBack,
}: {
  confirmLabel: string
  onConfirm: (reason: string) => Promise<void> | void
  onBack: () => void
}) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!reason.trim()) {
      setError('Informe o motivo do cancelamento.')
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
        label="Motivo do cancelamento"
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
