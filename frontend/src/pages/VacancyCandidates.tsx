import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, formatDateTime, type VacancyCandidates } from '../api'
import CancelReasonForm from '../components/CancelReasonForm'
import { Alert, Badge, Button } from '../components/ui'

/** Seção "Candidatos" do detalhe da vaga: aprovar, recusar e ver a equipe (US42). */
export default function VacancyCandidatesSection({
  vacancyId,
  onChange,
}: {
  vacancyId: number | string
  onChange?: () => void
}) {
  const [data, setData] = useState<VacancyCandidates | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [cancelling, setCancelling] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await api<VacancyCandidates>(`/api/vacancies/${vacancyId}/candidates/`))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível carregar os candidatos.')
    }
  }, [vacancyId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  async function decide(id: number, action: 'approve' | 'reject') {
    setError('')
    try {
      await api(`/api/applications/${id}/${action}/`, { method: 'POST' })
      await load()
      onChange?.()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível concluir a operação.')
      await load()
    }
  }

  async function cancelAssignment(id: number, reason: string) {
    setError('')
    try {
      await api(`/api/assignments/${id}/cancel-by-company/`, { method: 'POST', body: { reason } })
      setCancelling(null)
      setNotice('Turno cancelado. O valor da posição foi estornado e o prestador foi avisado.')
      onChange?.()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível cancelar o turno.')
    }
    await load()
  }

  if (!data) return error ? <Alert tone="error">{error}</Alert> : null

  return (
    <section aria-labelledby="candidatos-titulo">
      <h2 id="candidatos-titulo">Candidatos</h2>
      {error && <Alert tone="error">{error}</Alert>}
      {notice && <Alert tone="success">{notice}</Alert>}
      {data.candidates.length === 0 && <p>Nenhum candidato pendente.</p>}
      <ul>
        {data.candidates.map((c) => (
          <li key={c.id}>
            {c.photo_url && <img src={c.photo_url} alt={`Foto de ${c.name}`} width={48} height={48} />}
            <strong>{c.name}</strong> {c.verified && <Badge tone="success">Verificado</Badge>}
            <p>
              {c.completed_shifts} turnos concluídos · candidatou-se em {formatDateTime(c.applied_at)}
            </p>
            <div className="acoes">
              <Button disabled={data.team_complete} onClick={() => decide(c.id, 'approve')}>
                {data.team_complete ? 'Equipe completa' : 'Aprovar'}
              </Button>
              <Button variant="secondary" onClick={() => decide(c.id, 'reject')}>
                Recusar
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {data.team.length > 0 && (
        <>
          <h3>Equipe</h3>
          <ul>
            {data.team.map((m) => (
              <li key={m.id}>
                {m.first_name} · {m.phone || 'sem telefone'} <Badge>{m.status_label}</Badge>
                {m.status === 'CONFIRMADA' &&
                  (cancelling === m.id ? (
                    <CancelReasonForm
                      confirmLabel="Confirmar cancelamento"
                      onConfirm={(reason) => cancelAssignment(m.id, reason)}
                      onBack={() => setCancelling(null)}
                    />
                  ) : (
                    <Button
                      variant="secondary"
                      aria-label={`Cancelar ${m.first_name}`}
                      onClick={() => {
                        setError('')
                        setNotice('')
                        setCancelling(m.id)
                      }}
                    >
                      Cancelar
                    </Button>
                  ))}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
