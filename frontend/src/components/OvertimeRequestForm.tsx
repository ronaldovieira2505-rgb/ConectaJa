import { useState, type FormEvent } from 'react'
import { brl, type OvertimeOption } from '../api'
import { Button, Field, SelectField } from './ui'

/** "40,50" → 4050; 0 se não for um número válido. */
function toCents(text: string): number {
  const value = Number(text.replace(/\./g, '').replace(',', '.'))
  return Number.isFinite(value) ? Math.round(value * 100) : 0
}

function fromCents(cents: number): string {
  return (cents / 100).toFixed(2).replace('.', ',')
}

/** "Pedir hora extra" (US52): de 30 min a 4 h e o valor, nunca abaixo da hora do turno. */
export default function OvertimeRequestForm({
  options,
  onConfirm,
  onBack,
}: {
  options: OvertimeOption[]
  onConfirm: (minutes: number, amountCents: number) => Promise<void> | void
  onBack: () => void
}) {
  const [minutes, setMinutes] = useState(options[0]?.minutes ?? 30)
  const option = options.find((o) => o.minutes === minutes) ?? options[0]
  const [amount, setAmount] = useState(fromCents(option?.min_amount_cents ?? 0))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  function choose(value: number) {
    setMinutes(value)
    const next = options.find((o) => o.minutes === value)
    if (next && toCents(amount) < next.min_amount_cents) setAmount(fromCents(next.min_amount_cents))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const cents = toCents(amount)
    if (!option || cents < option.min_amount_cents) {
      setError(`O valor mínimo para ${option?.label ?? 'essa duração'} é ${brl(option?.min_amount_cents ?? 0)}.`)
      return
    }
    setError('')
    setBusy(true)
    try {
      await onConfirm(minutes, cents)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <SelectField
        label="Quanto tempo a mais"
        value={minutes}
        onChange={(event) => choose(Number(event.target.value))}
      >
        {options.map((o) => (
          <option key={o.minutes} value={o.minutes}>
            {o.label}
          </option>
        ))}
      </SelectField>
      <Field
        label="Valor da extensão (R$)"
        inputMode="decimal"
        value={amount}
        onChange={(event) => setAmount(event.target.value)}
        aria-invalid={error ? true : undefined}
      />
      <p className="sub">
        Mínimo de {brl(option?.min_amount_cents ?? 0)}, proporcional ao valor por hora do turno. O
        prestador é avisado e responde no app; sem resposta no prazo ou até o fim do turno, o pedido
        expira. Você só paga se ele aceitar.
      </p>
      {error && (
        <p role="alert" className="erro">
          {error}
        </p>
      )}
      <div className="acoes">
        <Button type="submit" busy={busy}>
          Enviar pedido
        </Button>
        <Button type="button" variant="secondary" onClick={onBack}>
          Voltar
        </Button>
      </div>
    </form>
  )
}
