import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, formatDateTime, type Candidate, type VacancyCandidates } from '../api'
import Avatar from '../components/Avatar'
import CancelReasonForm from '../components/CancelReasonForm'
import PortfolioThumbs from '../components/PortfolioThumbs'
import { Alert, Badge, Button } from '../components/ui'

function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo' })
}

/** Nota média e avaliações recentes do candidato (US40). A nota só informa; não aprova nem ordena. */
function CandidateRating({ candidate }: { candidate: Candidate }) {
  const [open, setOpen] = useState(false)
  const count = candidate.rating_count ?? 0
  const reviews = candidate.recent_reviews ?? []
  if (count === 0 || candidate.rating_avg == null) return <p>Novo na plataforma</p>
  const average = candidate.rating_avg.toLocaleString('pt-BR', { minimumFractionDigits: 1 })
  return (
    <div>
      <p>
        ★ {average} · {count} {count === 1 ? 'turno avaliado' : 'turnos avaliados'}
      </p>
      {reviews.length > 0 && (
        <>
          <Button
            variant="secondary"
            aria-expanded={open}
            aria-label={`${open ? 'Ocultar' : 'Ver'} avaliações de ${candidate.name}`}
            onClick={() => setOpen(!open)}
          >
            {open ? 'Ocultar avaliações' : 'Ver avaliações'}
          </Button>
          {open && (
            <ul aria-label={`Avaliações de ${candidate.name}`}>
              {reviews.map((r, i) => (
                <li key={i}>
                  <strong>★ {r.rating}</strong> · {formatDay(r.created_at)} · {r.company_name}
                  {r.comment && <p>{r.comment}</p>}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

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

  async function toggleAutoCall(enabled: boolean) {
    setError('')
    try {
      await api(`/api/vacancies/${vacancyId}/waitlist-auto-call/`, {
        method: 'POST',
        body: { enabled },
      })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível salvar a configuração.')
    }
    await load()
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
      {data.team_complete && (
        <>
          <h3>Lista de espera</h3>
          <label>
            <input
              type="checkbox"
              checked={data.auto_call_waitlist ?? true}
              onChange={(e) => toggleAutoCall(e.target.checked)}
            />{' '}
            Chamar automaticamente da lista de espera
          </label>
          <p>
            Se uma posição for liberada por falta ou cancelamento do prestador, o primeiro da lista
            que puder trabalhar é aprovado automaticamente.
          </p>
        </>
      )}
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {data.candidates.map((c) => (
          <li key={c.id} className="rounded-cartao bg-white p-4">
            {c.waitlist_position != null && (
              <Badge>{`${c.waitlist_position}º na lista de espera`}</Badge>
            )}
            <div className="flex items-center gap-3">
              <Avatar src={c.photo_url} name={c.name} className="size-12" />
              <strong>{c.name}</strong> {c.verified && <Badge tone="success">Verificado</Badge>}
            </div>
            {(c.skills ?? []).length > 0 && (
              <p className="marcadores" aria-label={`Experiência de ${c.name}`}>
                {(c.skills ?? []).map((skill) => (
                  <Badge key={skill.value} tone={skill.matches_vacancy ? 'info' : 'neutral'}>
                    {skill.label}
                    {skill.matches_vacancy && ' · categoria da vaga'}
                  </Badge>
                ))}
              </p>
            )}
            {c.bio && <p className="descricao">{c.bio}</p>}
            <PortfolioThumbs photos={c.portfolio ?? []} name={c.name} />
            <p>
              {c.completed_shifts} turnos concluídos · {c.no_shows_30d ?? 0}{' '}
              {(c.no_shows_30d ?? 0) === 1 ? 'falta' : 'faltas'} nos últimos{' '}
              {data.no_show_window_days ?? 30} dias · candidatou-se em {formatDateTime(c.applied_at)}
            </p>
            <CandidateRating candidate={c} />
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
