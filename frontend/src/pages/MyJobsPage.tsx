import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api,
  brl,
  formatShift,
  formatTime,
  type JobGroupKey,
  type JobItem,
  type MyJobs,
} from '../api'
import { Alert, Badge, Button, Card, Loading } from '../components/ui'
import VacancyCover from '../components/VacancyCover'

const GROUPS: { key: JobGroupKey; title: string }[] = [
  { key: 'in_progress', title: 'Em andamento' },
  { key: 'upcoming', title: 'Próximos turnos' },
  { key: 'waiting', title: 'Aguardando' },
  { key: 'completed', title: 'Concluídas' },
  { key: 'closed', title: 'Encerradas' },
]

function badgeTone(status: string): 'neutral' | 'success' | 'warning' | 'info' {
  if (status === 'PENDENTE') return 'warning'
  if (['CONFIRMADA', 'PAGA', 'APROVADA'].includes(status)) return 'success'
  if (['EM_EXECUCAO', 'AGUARDANDO_VALIDACAO', 'CONTESTADA'].includes(status)) return 'info'
  return 'neutral'
}

/** Meus trabalhos (US38): candidaturas e alocações do prestador agrupadas por situação. */
export default function MyJobsPage() {
  const [jobs, setJobs] = useState<MyJobs | null>(null)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [notes, setNotes] = useState<
    Record<number, { tone: 'error' | 'success'; text: string } | undefined>
  >({})
  const [busyId, setBusyId] = useState<number | null>(null)
  const [confirmingId, setConfirmingId] = useState<number | null>(null)
  const [cancellingId, setCancellingId] = useState<number | null>(null)

  function load() {
    return api<MyJobs>('/api/workers/me/jobs/')
      .then(setJobs)
      .catch((err: Error) => setError(err.message))
  }

  useEffect(() => {
    void load()
  }, [])

  function say(item: JobItem, tone: 'error' | 'success', text: string) {
    setNotes((current) => ({ ...current, [item.id]: { tone, text } }))
  }

  async function checkIn(item: JobItem) {
    setNotes((current) => ({ ...current, [item.id]: undefined }))
    if (!navigator.geolocation) {
      say(item, 'error', 'Seu navegador não oferece localização. Use outro navegador ou aparelho.')
      return
    }
    setBusyId(item.id)
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const done = await api<JobItem>(`/api/assignments/${item.id}/check-in/`, {
            method: 'POST',
            body: {
              lat: position.coords.latitude,
              lng: position.coords.longitude,
              accuracy: position.coords.accuracy,
            },
          })
          await load()
          say(item, 'success', `Check-in feito às ${formatTime(done.check_in_at ?? '')}`)
        } catch (err) {
          say(item, 'error', (err as Error).message)
        } finally {
          setBusyId(null)
        }
      },
      (geoError) => {
        setBusyId(null)
        say(
          item,
          'error',
          geoError.code === 1
            ? 'A permissão de localização está bloqueada. Ative a localização para este site nas configurações do navegador (cadeado ao lado do endereço) e tente de novo.'
            : 'Não foi possível obter sua localização. Verifique o GPS e tente de novo.',
        )
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    )
  }

  async function checkOut(item: JobItem) {
    setConfirmingId(null)
    setBusyId(item.id)
    try {
      await api(`/api/assignments/${item.id}/check-out/`, { method: 'POST' })
      await load()
    } catch (err) {
      say(item, 'error', (err as Error).message)
    } finally {
      setBusyId(null)
    }
  }

  async function cancelParticipation(item: JobItem) {
    setCancellingId(null)
    setBusyId(item.id)
    try {
      await api(`/api/assignments/${item.id}/cancel-by-worker/`, { method: 'POST' })
      await load()
    } catch (err) {
      say(item, 'error', (err as Error).message)
    } finally {
      setBusyId(null)
    }
  }

  async function withdraw(item: JobItem) {
    setActionError('')
    try {
      await api(`/api/applications/${item.id}/withdraw/`, { method: 'POST' })
      await load()
    } catch (err) {
      setActionError((err as Error).message)
    }
  }

  if (error) return <Alert tone="error">{error}</Alert>
  if (!jobs) return <Loading />

  return (
    <>
      <h1>Meus trabalhos</h1>
      {actionError && <Alert tone="error">{actionError}</Alert>}
      {GROUPS.every((group) => jobs.groups[group.key].length === 0) && (
        <Card>
          <div className="vazio">
            <h2>Nenhum trabalho ainda</h2>
            <p>Suas candidaturas e turnos aparecem aqui.</p>
            <Link to="/vagas" className="btn btn-primary">
              Buscar vagas
            </Link>
          </div>
        </Card>
      )}
      {GROUPS.map((group) => {
        const items = jobs.groups[group.key]
        // Grupo vazio não ocupa a tela: só aparece o que tem algo para o prestador ver ou fazer.
        if (items.length === 0) return null
        return (
          <section key={group.key} aria-labelledby={`grupo-${group.key}`}>
            <h2 id={`grupo-${group.key}`}>
              {group.title}{' '}
              <span className="text-tinta-media" aria-hidden="true">
                · {items.length}
              </span>
            </h2>
            {items.map((item) => (
              <Card key={`${item.kind}-${item.id}`}>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
                  <VacancyCover
                    photoUrl={item.photo_url}
                    category={item.category}
                    className="size-16 shrink-0 rounded-2xl"
                  />
                  <div className="flex min-w-[12rem] flex-1 flex-col gap-1">
                    <h3 className="m-0 text-[17px] leading-6 tracking-normal">
                      <Link to={`/vagas/${item.vacancy_id}`}>{item.title}</Link>
                    </h3>
                    <p className="m-0 text-[13px] leading-5 text-tinta-media">
                      <span>{item.company_name}</span> ·{' '}
                      {formatShift(item.starts_at, item.ends_at)}
                    </p>
                    <p className="marcadores m-0">
                      <Badge tone={badgeTone(item.status)}>
                        {item.status === 'CONTESTADA' ? 'Horas contestadas' : item.status_label}
                      </Badge>
                    </p>
                  </div>
                  <p className="m-0 ml-auto flex shrink-0 flex-col items-end">
                    <span className="text-[12px] leading-4 text-tinta-media">Você recebe</span>
                    <span className="text-[20px] leading-7">{brl(item.net_cents)}</span>
                  </p>
                </div>
                {item.kind === 'assignment' && (
                  <>
                    {item.status === 'CONFIRMADA' && item.can_check_in && (
                      <div className="acoes">
                        <Button busy={busyId === item.id} onClick={() => checkIn(item)}>
                          Cheguei
                        </Button>
                      </div>
                    )}
                    {item.status === 'CONFIRMADA' &&
                      !item.can_check_in &&
                      item.check_in_opens_at &&
                      item.check_in_closes_at &&
                      Date.now() < new Date(item.check_in_closes_at).getTime() && (
                        <p>O check-in abre às {formatTime(item.check_in_opens_at)}.</p>
                      )}
                    {item.status === 'CONTESTADA' && (
                      <Alert tone="error">
                        Horas contestadas pela empresa.
                        {item.contest_reason && <> Motivo: {item.contest_reason}</>}
                      </Alert>
                    )}
                    {item.check_in_at && (
                      <p>
                        Check-in feito às {formatTime(item.check_in_at)}
                        {item.check_out_at &&
                          ` · Saída às ${formatTime(item.check_out_at)}${
                            item.check_out_auto ? ' (registrada automaticamente)' : ''
                          }`}
                      </p>
                    )}
                    {item.can_check_out &&
                      (confirmingId === item.id ? (
                        <div className="acoes">
                          <Button busy={busyId === item.id} onClick={() => checkOut(item)}>
                            Confirmar encerramento
                          </Button>
                          <Button variant="secondary" onClick={() => setConfirmingId(null)}>
                            Voltar
                          </Button>
                        </div>
                      ) : (
                        <div className="acoes">
                          <Button onClick={() => setConfirmingId(item.id)}>Encerrar turno</Button>
                        </div>
                      ))}
                    {item.can_cancel &&
                      (cancellingId === item.id ? (
                        <>
                          <Alert tone={item.cancel_is_late ? 'error' : 'success'}>
                            {item.cancel_is_late
                              ? item.cancel_warning
                              : 'Cancelando agora você não sofre penalidade.'}
                          </Alert>
                          <div className="acoes">
                            <Button
                              busy={busyId === item.id}
                              onClick={() => cancelParticipation(item)}
                            >
                              Confirmar cancelamento
                            </Button>
                            <Button variant="secondary" onClick={() => setCancellingId(null)}>
                              Voltar
                            </Button>
                          </div>
                        </>
                      ) : (
                        <div className="acoes">
                          <Button variant="secondary" onClick={() => setCancellingId(item.id)}>
                            Cancelar participação
                          </Button>
                        </div>
                      ))}
                    {notes[item.id] && (
                      <Alert tone={notes[item.id]!.tone}>{notes[item.id]!.text}</Alert>
                    )}
                  </>
                )}
                {item.can_withdraw && (
                  <div className="acoes">
                    <Button variant="secondary" onClick={() => withdraw(item)}>
                      Desistir
                    </Button>
                  </div>
                )}
              </Card>
            ))}
          </section>
        )
      })}
    </>
  )
}
