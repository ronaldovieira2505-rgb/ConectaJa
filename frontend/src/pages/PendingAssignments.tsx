import { useCallback, useEffect, useState } from 'react'
import {
  api,
  ApiError,
  brl,
  formatDateTime,
  formatDayMonthTime,
  formatRemaining,
  formatTime,
  type ContestedAssignment,
  type PendingArrivalJustification,
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
  const [contested, setContested] = useState<ContestedAssignment[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [contestingId, setContestingId] = useState<number | null>(null)
  const [arrivals, setArrivals] = useState<PendingArrivalJustification[]>([])
  const [refusingId, setRefusingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    const query = vacancyId !== undefined ? `?vacancy=${vacancyId}` : ''
    try {
      const data = await api<{
        results: PendingAssignment[]
        contested?: ContestedAssignment[]
        arrival_justifications?: PendingArrivalJustification[]
      }>(`/api/company/assignments/pending/${query}`)
      setItems(data.results)
      setContested(data.contested ?? [])
      setArrivals(data.arrival_justifications ?? [])
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

  async function decideArrival(assignmentId: number, confirm: boolean, reason = '') {
    setError('')
    setNotice('')
    try {
      await api(`/api/assignments/${assignmentId}/arrival-justification/decide/`, {
        method: 'POST',
        body: { confirm, reason },
      })
      setRefusingId(null)
      setNotice(
        confirm
          ? 'Chegada confirmada. O turno está em execução.'
          : 'Justificativa recusada. O prestador foi avisado.',
      )
      await load()
      onChange?.()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível registrar a decisão.')
      await load()
    }
  }

  if (!items) return error ? <Alert tone="error">{error}</Alert> : null

  return (
    <section aria-labelledby="confirmar-titulo">
      {/* Na página própria o título já está no topo; aqui fica só para leitores de tela. */}
      <h2 id="confirmar-titulo" className={vacancyId === undefined ? 'sr-only' : undefined}>
        Confirmar presença
      </h2>
      {error && <Alert tone="error">{error}</Alert>}
      {notice && <Alert tone="success">{notice}</Alert>}
      {arrivals.length > 0 && (
        <>
          <h3>Chegadas para confirmar</h3>
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {arrivals.map((j) => (
              <li key={j.id} className="rounded-cartao bg-white p-4">
                <strong>{j.worker_first_name}</strong>
                {vacancyId === undefined && <> · {j.vacancy_title}</>}{' '}
                <Badge tone="warning">Sem check-in pelo celular</Badge>
                <dl className="linhas">
                  <div>
                    <dt>Turno</dt>
                    <dd>
                      {formatTime(j.starts_at)} às {formatTime(j.ends_at)}
                    </dd>
                  </div>
                  <div>
                    <dt>Pedido enviado</dt>
                    <dd>{formatTime(j.created_at)}</dd>
                  </div>
                  <div>
                    <dt>Motivo</dt>
                    <dd>{j.reason_label}</dd>
                  </div>
                </dl>
                {j.text && <p>“{j.text}”</p>}
                <p className="sub">
                  Ao confirmar, o check-in fica registrado no horário do pedido. Sem resposta até o
                  fim do turno, a equipe ConectaJá decide.
                </p>
                {refusingId === j.id ? (
                  <CancelReasonForm
                    label="Motivo da recusa"
                    emptyMessage="Informe o motivo da recusa."
                    confirmLabel="Recusar justificativa"
                    onConfirm={(reason) => decideArrival(j.assignment_id, false, reason)}
                    onBack={() => setRefusingId(null)}
                  />
                ) : (
                  <div className="acoes">
                    <Button onClick={() => decideArrival(j.assignment_id, true)}>
                      Confirmar chegada
                    </Button>
                    <Button variant="secondary" onClick={() => setRefusingId(j.id)}>
                      Recusar
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
          {items.length > 0 && <h3>Horas a conferir</h3>}
        </>
      )}
      {items.length === 0 && arrivals.length === 0 && (
        <p>Nenhuma presença aguardando confirmação.</p>
      )}
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {items.map((a) => (
          <li key={a.id} className="rounded-cartao bg-white p-4">
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
      {contested.length > 0 && (
        <>
          <h3>Horas contestadas</h3>
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {contested.map((c) => (
              <li key={c.id} className="rounded-cartao bg-white p-4">
                <strong>{c.worker_first_name}</strong>
                {vacancyId === undefined && <> · {c.vacancy_title}</>}{' '}
                <Badge tone="info">Contestada</Badge>
                <p>Seu motivo: {c.contest_reason}</p>
                {c.contest_response_at ? (
                  <p>
                    Versão do prestador, enviada em {formatDayMonthTime(c.contest_response_at)}:{' '}
                    {c.contest_response}
                  </p>
                ) : (
                  <p className="sub">O prestador ainda não respondeu. A equipe vai decidir.</p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
