import { useCallback, useEffect, useState } from 'react'
import {
  api,
  ApiError,
  brl,
  formatDateTime,
  formatRemaining,
  formatTime,
  type PendingAssignment,
} from '../api'
import CancelReasonForm from '../components/CancelReasonForm'
import { Alert, Badge, Button } from '../components/ui'

/** Horas a conferir: previsto × registrado e aprovação com liberação do pagamento (US56/US59). */
export default function PendingAssignmentsSection({
  vacancyId,
  onChange,
}: {
  vacancyId?: number | string
  onChange?: () => void
}) {
  const [items, setItems] = useState<PendingAssignment[] | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [contestingId, setContestingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    const query = vacancyId !== undefined ? `?vacancy=${vacancyId}` : ''
    try {
      const data = await api<{ results: PendingAssignment[] }>(
        `/api/company/assignments/pending/${query}`,
      )
      setItems(data.results)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível carregar as horas a conferir.')
    }
  }, [vacancyId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  async function approve(id: number) {
    setError('')
    setNotice('')
    try {
      const result = await api<{ payment_pending: boolean }>(`/api/assignments/${id}/approve/`, {
        method: 'POST',
      })
      setNotice(
        result.payment_pending
          ? 'Horas aprovadas. O pagamento será liberado no próximo processamento.'
          : 'Presença confirmada e pagamento liberado.',
      )
      await load()
      onChange?.()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível aprovar as horas.')
      await load()
    }
  }

  async function contest(id: number, reason: string) {
    setError('')
    setNotice('')
    try {
      await api(`/api/assignments/${id}/contest/`, { method: 'POST', body: { reason } })
      setContestingId(null)
      setNotice('Horas contestadas. A equipe vai analisar e avisar as partes.')
      await load()
      onChange?.()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível contestar as horas.')
      await load()
    }
  }

  if (!items) return error ? <Alert tone="error">{error}</Alert> : null

  return (
    <section aria-labelledby="confirmar-titulo">
      <h2 id="confirmar-titulo">Confirmar presença</h2>
      {error && <Alert tone="error">{error}</Alert>}
      {notice && <Alert tone="success">{notice}</Alert>}
      {items.length === 0 && <p>Nenhuma presença aguardando confirmação.</p>}
      <ul>
        {items.map((a) => (
          <li key={a.id}>
            <strong>{a.worker_first_name}</strong>
            {vacancyId === undefined && <> · {a.vacancy_title}</>}{' '}
            {a.check_out_auto && <Badge tone="warning">Check-out automático</Badge>}
            <dl className="linhas">
              <div>
                <dt>Previsto</dt>
                <dd>
                  {formatTime(a.starts_at)} às {formatTime(a.ends_at)}
                </dd>
              </div>
              <div>
                <dt>Registrado</dt>
                <dd>
                  {a.check_in_at ? formatTime(a.check_in_at) : '—'} às {formatTime(a.check_out_at)}
                </dd>
              </div>
              {a.check_in_distance_m !== null && (
                <div>
                  <dt>Distância do check-in</dt>
                  <dd>{a.check_in_distance_m} m</dd>
                </div>
              )}
              <div>
                <dt>Valor</dt>
                <dd>{brl(a.gross_cents)}</dd>
              </div>
            </dl>
            <p className="sub" title={formatDateTime(a.auto_approve_at)}>
              {a.auto_approve_in_seconds > 0
                ? `Aprovação automática em ${formatRemaining(a.auto_approve_in_seconds)}`
                : 'Aprovação automática no próximo processamento'}
            </p>
            {contestingId === a.id ? (
              <CancelReasonForm
                label="Motivo da contestação"
                emptyMessage="Informe o motivo da contestação."
                confirmLabel="Enviar contestação"
                onConfirm={(reason) => contest(a.id, reason)}
                onBack={() => setContestingId(null)}
              />
            ) : (
              <div className="acoes">
                <Button onClick={() => approve(a.id)}>Confirmar presença e liberar pagamento</Button>
                {a.can_contest && (
                  <Button variant="secondary" onClick={() => setContestingId(a.id)}>
                    Contestar
                  </Button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
