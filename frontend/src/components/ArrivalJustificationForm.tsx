import { useId, useState } from 'react'
import { ARRIVAL_REASONS, type ArrivalReason } from '../api'
import { Alert, Button } from './ui'

const TEXT_MAX = 300

/** "Não consigo registrar a chegada" (US51): motivo da lista e explicação de até 300 caracteres. */
export default function ArrivalJustificationForm({
  busy,
  onSubmit,
  onCancel,
}: {
  busy: boolean
  onSubmit: (reason: ArrivalReason, text: string) => void
  onCancel: () => void
}) {
  const [reason, setReason] = useState<ArrivalReason | ''>('')
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const id = useId()
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (!reason) {
          setError('Escolha o motivo.')
          return
        }
        if (reason === 'OUTRO' && !text.trim()) {
          setError('Explique o que aconteceu.')
          return
        }
        setError('')
        onSubmit(reason, text.trim())
      }}
    >
      <fieldset className="m-0 border-0 p-0">
        <legend>Por que você não consegue registrar a chegada?</legend>
        {ARRIVAL_REASONS.map((option) => (
          <label key={option.value} className="block">
            <input
              type="radio"
              name={`motivo-${id}`}
              value={option.value}
              checked={reason === option.value}
              onChange={() => setReason(option.value)}
            />{' '}
            {option.label}
          </label>
        ))}
      </fieldset>
      <div className="field">
        <label htmlFor={`explicacao-${id}`}>
          Explicação {reason === 'OUTRO' ? '' : '(opcional)'}
        </label>
        <textarea
          id={`explicacao-${id}`}
          maxLength={TEXT_MAX}
          rows={3}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <small>
          {text.length}/{TEXT_MAX}
        </small>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <p>
        A empresa vai confirmar a sua chegada. Enquanto ela não responder, o turno não conta
        como falta. Só é possível enviar uma justificativa por turno.
      </p>
      <div className="acoes">
        <Button type="submit" busy={busy}>
          Enviar justificativa
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Voltar
        </Button>
      </div>
    </form>
  )
}
