import { useEffect, useId, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api,
  type ArrivalJustification,
  type ArrivalReason,
  brl,
  formatDayMonthTime,
  formatShift,
  formatTime,
  type JobGroupKey,
  type JobItem,
  type MyJobs,
} from '../api'
import ArrivalJustificationForm from '../components/ArrivalJustificationForm'
import JobsTabs from '../components/JobsTabs'
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

/** Formulário de "Avaliar empresa" (US64): nota de 1 a 5 e comentário opcional de até 500 caracteres. */
function ReviewCompanyForm({
  busy,
  onSubmit,
  onCancel,
}: {
  busy: boolean
  onSubmit: (rating: number, comment: string) => void
  onCancel: () => void
}) {
  const [rating, setRating] = useState(0)
  const [comment, setComment] = useState('')
  const id = useId()
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (rating > 0) onSubmit(rating, comment)
      }}
    >
      <fieldset className="m-0 border-0 p-0">
        <legend>Sua nota para a empresa</legend>
        <div className="acoes">
          {[1, 2, 3, 4, 5].map((value) => (
            <label key={value}>
              <input
                type="radio"
                name={`nota-${id}`}
                value={value}
                checked={rating === value}
                onChange={() => setRating(value)}
              />{' '}
              {value} {value === 1 ? 'estrela' : 'estrelas'}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="field">
        <label htmlFor={`comentario-${id}`}>Comentário (opcional)</label>
        <textarea
          id={`comentario-${id}`}
          maxLength={500}
          rows={3}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
        <small>{comment.length}/500</small>
      </div>
      <p>A avaliação é definitiva e não pode ser editada depois de enviada.</p>
      <div className="acoes">
        <Button type="submit" busy={busy} disabled={rating === 0}>
          Enviar avaliação
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Voltar
        </Button>
      </div>
    </form>
  )
}

const RESPONSE_MIN = 10
const RESPONSE_MAX = 1000
const RESPONSE_ERROR = 'A sua versão deve ter de 10 a 1.000 caracteres.'

/** "Sua versão" (US58): texto de 10 a 1.000 caracteres, enviado uma única vez. */
function ContestResponseForm({
  busy,
  onSubmit,
}: {
  busy: boolean
  onSubmit: (text: string) => void
}) {
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const id = useId()
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        const size = text.trim().length
        if (size < RESPONSE_MIN || size > RESPONSE_MAX) {
          setError(RESPONSE_ERROR)
          return
        }
        setError('')
        onSubmit(text.trim())
      }}
    >
      <div className="field">
        <label htmlFor={`versao-${id}`}>Sua versão</label>
        <textarea
          id={`versao-${id}`}
          rows={4}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <small>{text.length}/1000</small>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <p>A resposta é única e não pode ser editada depois de enviada.</p>
      <div className="acoes">
        <Button type="submit" busy={busy}>
          Enviar resposta
        </Button>
      </div>
    </form>
  )
}

/** Situação do pedido de confirmação de chegada (US51). Confirmado aparece no horário do check-in. */
function ArrivalJustificationStatus({ justification }: { justification: ArrivalJustification }) {
  if (justification.status === 'PENDENTE') {
    return (
      <Alert>
        Justificativa enviada ({justification.reason_label}). Aguardando a empresa confirmar a sua
        chegada. Enquanto isso, o turno não conta como falta.
      </Alert>
    )
  }
  if (justification.status === 'COM_ADMIN') {
    return (
      <Alert>
        A empresa não respondeu à sua justificativa. A equipe ConectaJá vai decidir sobre a sua
        chegada.
      </Alert>
    )
  }
  if (justification.status === 'RECUSADA') {
    return (
      <Alert tone="error">
        Sua justificativa de chegada foi recusada.
        {justification.decision_reason && <> Motivo: {justification.decision_reason}</>}
      </Alert>
    )
  }
  return null
}

/** Pedido de hora extra da empresa (US53): valores antes de responder e o resultado. */
function OvertimeOffer({
  item,
  busy,
  onAccept,
  onDecline,
}: {
  item: JobItem
  busy: boolean
  onAccept: () => void
  onDecline: () => void
}) {
  const request = item.overtime
  if (!request) return null
  if (request.status === 'AGUARDANDO_PRESTADOR' && item.can_respond_overtime) {
    return (
      <Alert>
        <p className="m-0">
          A empresa pediu <strong>{request.minutes_label} a mais</strong>. Valor bruto{' '}
          {brl(request.amount_cents)} · você recebe <strong>{brl(request.net_cents)}</strong> (já
          com a taxa descontada). Responda até {formatTime(request.expires_at)}.
        </p>
        <p className="m-0">Recusar não gera penalidade.</p>
        <div className="acoes">
          <Button busy={busy} onClick={onAccept}>
            Aceitar hora extra
          </Button>
          <Button variant="secondary" onClick={onDecline}>
            Recusar
          </Button>
        </div>
      </Alert>
    )
  }
  if (request.status === 'ACEITO') {
    return (
      <p>
        Hora extra aceita: {request.minutes_label} a mais, você recebe {brl(request.net_cents)}.
        {item.extended_until && <> O turno agora termina às {formatTime(item.extended_until)}.</>}
      </p>
    )
  }
  if (request.status === 'RECUSADO') return <p className="sub">Você recusou a hora extra.</p>
  return null
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
  const [reviewingId, setReviewingId] = useState<number | null>(null)
  const [justifyingId, setJustifyingId] = useState<number | null>(null)

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

  async function reviewCompany(item: JobItem, rating: number, comment: string) {
    setBusyId(item.id)
    try {
      await api(`/api/assignments/${item.id}/review-company/`, {
        method: 'POST',
        body: { rating, comment },
      })
      setReviewingId(null)
      await load()
      say(item, 'success', 'Avaliação enviada. Obrigado!')
    } catch (err) {
      say(item, 'error', (err as Error).message)
    } finally {
      setBusyId(null)
    }
  }

  async function justifyArrival(item: JobItem, reason: ArrivalReason, text: string) {
    setBusyId(item.id)
    try {
      await api(`/api/assignments/${item.id}/arrival-justification/`, {
        method: 'POST',
        body: { reason, text },
      })
      setJustifyingId(null)
      await load()
      say(item, 'success', 'Justificativa enviada. A empresa foi avisada.')
    } catch (err) {
      say(item, 'error', (err as Error).message)
    } finally {
      setBusyId(null)
    }
  }

  async function answerOvertime(item: JobItem, action: 'accept' | 'decline') {
    if (!item.overtime) return
    setBusyId(item.id)
    try {
      await api(`/api/overtime/${item.overtime.id}/${action}/`, { method: 'POST' })
      await load()
      say(
        item,
        'success',
        action === 'accept'
          ? 'Hora extra aceita. A empresa foi avisada.'
          : 'Hora extra recusada. A empresa foi avisada.',
      )
    } catch (err) {
      await load()
      say(item, 'error', (err as Error).message)
    } finally {
      setBusyId(null)
    }
  }

  async function respondToContest(item: JobItem, text: string) {
    setBusyId(item.id)
    try {
      await api(`/api/assignments/${item.id}/contest-response/`, {
        method: 'POST',
        body: { text },
      })
      await load()
      say(item, 'success', 'Resposta enviada. A equipe vai analisar as duas versões.')
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
      <JobsTabs />
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
                    {item.can_justify_arrival &&
                      (justifyingId === item.id ? (
                        <ArrivalJustificationForm
                          busy={busyId === item.id}
                          onSubmit={(reason, text) => justifyArrival(item, reason, text)}
                          onCancel={() => setJustifyingId(null)}
                        />
                      ) : (
                        <div className="acoes">
                          <Button variant="secondary" onClick={() => setJustifyingId(item.id)}>
                            Não consigo registrar a chegada
                          </Button>
                        </div>
                      ))}
                    {item.arrival_justification && (
                      <ArrivalJustificationStatus justification={item.arrival_justification} />
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
                    {item.can_respond_to_contest && (
                      <ContestResponseForm
                        busy={busyId === item.id}
                        onSubmit={(text) => respondToContest(item, text)}
                      />
                    )}
                    {item.contest_response && item.contest_response_at && (
                      <p>
                        Sua versão, enviada em {formatDayMonthTime(item.contest_response_at)}:{' '}
                        {item.contest_response}
                      </p>
                    )}
                    {item.check_in_at && (
                      <p>
                        Check-in feito às {formatTime(item.check_in_at)}
                        {item.check_in_confirmed_by_company && ' (confirmado pela empresa)'}
                        {item.check_out_at &&
                          ` · Saída às ${formatTime(item.check_out_at)}${
                            item.check_out_auto ? ' (registrada automaticamente)' : ''
                          }`}
                      </p>
                    )}
                    <OvertimeOffer
                      item={item}
                      busy={busyId === item.id}
                      onAccept={() => answerOvertime(item, 'accept')}
                      onDecline={() => answerOvertime(item, 'decline')}
                    />
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
                    {item.can_review &&
                      (reviewingId === item.id ? (
                        <ReviewCompanyForm
                          busy={busyId === item.id}
                          onSubmit={(rating, comment) => reviewCompany(item, rating, comment)}
                          onCancel={() => setReviewingId(null)}
                        />
                      ) : (
                        <div className="acoes">
                          <Button variant="secondary" onClick={() => setReviewingId(item.id)}>
                            Avaliar empresa
                          </Button>
                        </div>
                      ))}
                    {item.my_review && (
                      <p>
                        Você avaliou a empresa: {item.my_review.rating} de 5
                        {item.my_review.comment && ` · “${item.my_review.comment}”`}
                      </p>
                    )}
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
