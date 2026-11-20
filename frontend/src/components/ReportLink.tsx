import { useId, useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import { useAuth } from '../authContext'
import { Alert, Button } from './ui'

export type ReportTarget = 'VAGA' | 'EMPRESA' | 'PRESTADOR'

const REASONS: Record<ReportTarget, { value: string; label: string }[]> = {
  VAGA: [
    { value: 'VAGA_FALSA', label: 'Vaga falsa ou golpe' },
    { value: 'PAGAMENTO_POR_FORA', label: 'Pedido de pagamento por fora' },
    { value: 'CONDICOES_DIFERENTES', label: 'Condições diferentes do anúncio' },
    { value: 'COMPORTAMENTO', label: 'Comportamento inadequado' },
    { value: 'OUTRO', label: 'Outro' },
  ],
  EMPRESA: [],
  PRESTADOR: [
    { value: 'COMPORTAMENTO', label: 'Comportamento inadequado' },
    { value: 'DANO_FURTO', label: 'Dano ou furto' },
    { value: 'ASSEDIO', label: 'Assédio' },
    { value: 'DOCUMENTO_FALSO', label: 'Documento ou identidade falsa' },
    { value: 'OUTRO', label: 'Outro' },
  ],
}
REASONS.EMPRESA = REASONS.VAGA

const MIN = 10
const MAX = 1000

/**
 * Link discreto "Denunciar" (US69/US70): abre o formulário com motivo e descrição de 10 a 1.000
 * caracteres. Visitante vai para o login e volta para a mesma página. `role` diz quem pode
 * denunciar esse alvo; os demais perfis não veem o link.
 */
export default function ReportLink({
  targetType,
  targetId,
  role,
  label = 'Denunciar',
  ariaLabel,
}: {
  targetType: ReportTarget
  targetId: number
  role: 'WORKER' | 'COMPANY'
  label?: string
  ariaLabel?: string
}) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const [sent, setSent] = useState('')
  const [busy, setBusy] = useState(false)
  const id = useId()

  if (user && user.role !== role) return null

  function start() {
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(location.pathname)}`)
      return
    }
    setSent('')
    setOpen(true)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!reason) {
      setError('Escolha o motivo.')
      return
    }
    const text = description.trim()
    if (text.length < MIN) {
      setError('Descreva o que aconteceu com pelo menos 10 caracteres.')
      return
    }
    setError('')
    setBusy(true)
    try {
      const result = await api<{ detail: string }>('/api/reports/', {
        method: 'POST',
        body: { target_type: targetType, target_id: targetId, reason, description: text },
      })
      setSent(result.detail)
      setOpen(false)
      setReason('')
      setDescription('')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível enviar a denúncia.')
    } finally {
      setBusy(false)
    }
  }

  if (sent) return <Alert tone="success">{sent}</Alert>

  if (!open) {
    return (
      <button
        type="button"
        className="cursor-pointer border-0 bg-transparent p-0 text-[13px] text-tinta-media underline"
        aria-label={ariaLabel}
        onClick={start}
      >
        {label}
      </button>
    )
  }

  return (
    <form onSubmit={submit} noValidate aria-label="Denúncia">
      <fieldset className="m-0 border-0 p-0">
        <legend>Motivo da denúncia</legend>
        {REASONS[targetType].map((option) => (
          <label key={option.value} className="block">
            <input
              type="radio"
              name={`motivo-denuncia-${id}`}
              value={option.value}
              checked={reason === option.value}
              onChange={() => setReason(option.value)}
            />{' '}
            {option.label}
          </label>
        ))}
      </fieldset>
      <div className="field">
        <label htmlFor={`descricao-denuncia-${id}`}>O que aconteceu?</label>
        <textarea
          id={`descricao-denuncia-${id}`}
          rows={4}
          maxLength={MAX}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
        <small>
          {description.length}/{MAX}
        </small>
      </div>
      <p className="sub">A denúncia é confidencial: o denunciado não é avisado nem sabe quem denunciou.</p>
      {error && <Alert tone="error">{error}</Alert>}
      <div className="acoes">
        <Button type="submit" busy={busy}>
          Enviar denúncia
        </Button>
        <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
          Voltar
        </Button>
      </div>
    </form>
  )
}
