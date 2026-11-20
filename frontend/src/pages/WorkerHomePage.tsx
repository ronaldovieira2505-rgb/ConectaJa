import { Camera, FileText, Star } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api,
  brl,
  formatMonthYear,
  formatShift,
  type JobItem,
  type MyJobs,
  type WorkerProfile,
} from '../api'
import Avatar from '../components/Avatar'
import DeleteAccountCard from '../components/DeleteAccountCard'
import HistoryItem from '../components/HistoryItem'
import PortfolioCard from '../components/PortfolioCard'
import SkillsCard from '../components/SkillsCard'
import { Alert, Badge, Card, Loading } from '../components/ui'
import type { Tone } from '../status'

const DOCUMENT_STATUS: Record<string, string> = {
  PENDENTE_DOCUMENTOS: 'Pendente',
  EM_ANALISE: 'Em análise',
  APROVADO: 'Aprovado',
  REJEITADO: 'Rejeitado',
}

const VERIFICATION: Record<string, { label: string; tone: 'success' | 'warning' | 'info' | 'error' }> = {
  PENDENTE_DOCUMENTOS: { label: 'Cadastro incompleto', tone: 'warning' },
  EM_ANALISE: { label: 'Em análise', tone: 'info' },
  APROVADO: { label: 'Verificado', tone: 'success' },
  REJEITADO: { label: 'Cadastro rejeitado', tone: 'error' },
}

/** A lombada acompanha a verificação: colete enquanto depende do prestador. */
const PROFILE_TONES: Record<string, Tone> = {
  PENDENTE_DOCUMENTOS: 'colete',
  EM_ANALISE: 'uniforme',
  APROVADO: 'carimbo',
  REJEITADO: 'encerrada',
}

const HISTORY_SIZE = 5

function Stars({ rating }: { rating: number }) {
  return (
    <span className="inline-flex gap-0.5" role="img" aria-label={`Nota ${rating} de 5`}>
      {Array.from({ length: 5 }, (_, index) => (
        <Star
          key={index}
          className={`size-4 ${index < rating ? 'fill-colete text-colete' : 'text-regua'}`}
          strokeWidth={1.25}
          aria-hidden="true"
        />
      ))}
    </span>
  )
}

/** Perfil do prestador: foto, verificação, números, documentos, PIX e histórico de trabalho. */
export default function WorkerHomePage() {
  const [profile, setProfile] = useState<WorkerProfile | null>(null)
  const [history, setHistory] = useState<JobItem[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api<WorkerProfile>('/api/workers/me/')
      .then(setProfile)
      .catch(() => setError('Não foi possível carregar o seu perfil.'))
    api<MyJobs>('/api/workers/me/jobs/')
      .then((jobs) => setHistory(jobs.groups.completed))
      .catch(() => undefined) // sem histórico, o resto do perfil continua valendo
  }, [])

  if (error) return <Alert tone="error">{error}</Alert>
  if (!profile) return <Loading rows={2} />

  // Etapas opcionais (habilidades, US08) não bloqueiam a candidatura.
  const pending = profile.profile_steps.filter((step) => !step.done && !step.optional).length
  const approved = profile.verification_status === 'APROVADO'
  const verification = VERIFICATION[profile.verification_status] ?? VERIFICATION.PENDENTE_DOCUMENTOS
  const stats = profile.stats
  const documents = profile.documents ?? []
  const reviews = profile.reviews ?? []
  const canSendDocuments = ['PENDENTE_DOCUMENTOS', 'REJEITADO'].includes(profile.verification_status)

  return (
    <>
      <Card tone={PROFILE_TONES[profile.verification_status] ?? 'colete'}>
        <div className="flex flex-wrap items-center gap-5">
          <Avatar src={profile.photo_url} name={profile.full_name} />
          <div className="flex min-w-[12rem] flex-1 flex-col gap-2">
            <h1 className="m-0">{profile.full_name}</h1>
            <p className="marcadores m-0">
              <Badge tone={verification.tone}>{verification.label}</Badge>
              {profile.member_since && (
                <Badge>Desde {formatMonthYear(profile.member_since)}</Badge>
              )}
            </p>
            <p className="sub m-0">
              CPF {profile.cpf} · Telefone {profile.phone}
            </p>
          </div>
        </div>
        {stats && (
          <dl className="fatos">
            <div className="fato-destaque">
              <dt>Turnos concluídos</dt>
              <dd>{stats.completed_shifts}</dd>
            </div>
            <div className="fato-destaque">
              <dt>Total recebido</dt>
              <dd>{brl(stats.total_received_cents)}</dd>
            </div>
            <div className="fato-destaque">
              <dt>Avaliação</dt>
              <dd>
                {stats.rating_average === null
                  ? '—'
                  : stats.rating_average.toLocaleString('pt-BR', { minimumFractionDigits: 1 })}
                {stats.rating_count > 0 && (
                  <small className="ml-2 text-[13px] text-tinta-media">
                    {stats.rating_count} {stats.rating_count === 1 ? 'nota' : 'notas'}
                  </small>
                )}
              </dd>
            </div>
          </dl>
        )}
        {profile.verification_message && <Alert tone="info">{profile.verification_message}</Alert>}
      </Card>

      {!approved && (
        <Card>
          <h2>Complete seu perfil</h2>
          <p className="sub">
            {pending === 0
              ? 'Tudo enviado. Avisamos quando a verificação terminar.'
              : 'Termine estas etapas para se candidatar.'}
          </p>
          <ol className="etapas" aria-label="Etapas do perfil">
            {profile.profile_steps.map((step, index) => {
              const label =
                step.key === 'documentos'
                  ? (DOCUMENT_STATUS[step.status ?? ''] ?? 'Pendente')
                  : step.done
                    ? 'Concluída'
                    : step.optional
                      ? 'Opcional'
                      : 'Pendente'
              const target =
                step.key === 'documentos'
                  ? '/perfil/documentos'
                  : step.key === 'pix'
                    ? '/perfil/pix'
                    : `/prestador/perfil#${step.key}`
              return (
                <li key={step.key} className={step.done ? 'feita' : ''}>
                  <span className="etapa-num" aria-hidden="true">
                    {index + 1}
                  </span>{' '}
                  <span className="etapa-nome">{step.label}</span>
                  <Badge tone={step.done ? 'success' : step.optional ? 'neutral' : 'warning'}>
                    {label}
                  </Badge>
                  <Link to={target}>{step.done ? 'Ver' : 'Completar'}</Link>
                </li>
              )
            })}
          </ol>
        </Card>
      )}

      <SkillsCard profile={profile} onSaved={setProfile} />

      <PortfolioCard
        photos={profile.portfolio ?? []}
        onChange={(photos) => setProfile({ ...profile, portfolio: photos })}
      />

      <Card>
        <h2>Documentos</h2>
        <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 min-[520px]:grid-cols-3">
          {documents.map((document) => {
            const Icon = document.kind === 'SELFIE' ? Camera : FileText
            return (
              <li
                key={document.kind}
                className="flex flex-col items-start gap-2 rounded-[20px] bg-papel p-4"
              >
                <Icon className="size-6 text-tinta-media" strokeWidth={1.25} aria-hidden="true" />
                <span className="text-[15px] leading-6">{document.label}</span>
                {document.uploaded ? (
                  <Badge tone="success">Enviado</Badge>
                ) : approved ? (
                  <Badge>Sem arquivo</Badge>
                ) : (
                  <Badge tone="warning">Pendente</Badge>
                )}
                {document.url && (
                  <a href={document.url} target="_blank" rel="noreferrer" className="text-[13px]">
                    Abrir arquivo
                  </a>
                )}
              </li>
            )
          })}
        </ul>
        <div className="acoes">
          {canSendDocuments && (
            <Link to="/perfil/documentos" className="btn btn-secondary">
              {documents.some((document) => document.uploaded)
                ? 'Reenviar documentos'
                : 'Enviar documentos'}
            </Link>
          )}
          <Link to="/perfil/pix" className="btn btn-secondary">
            {profile.pix_key ? `PIX ${profile.pix_key}` : 'Cadastrar chave PIX'}
          </Link>
        </div>
      </Card>

      <Card>
        <h2>Histórico de trabalho</h2>
        {history.length === 0 ? (
          <div className="vazio">
            <p>Nenhum turno concluído ainda.</p>
            <Link to="/vagas" className="btn btn-primary">
              Buscar vagas
            </Link>
          </div>
        ) : (
          <>
            <ul className="m-0 list-none p-0">
              {history.slice(0, HISTORY_SIZE).map((job) => (
                <HistoryItem
                  key={`${job.kind}-${job.id}`}
                  to={`/vagas/${job.vacancy_id}`}
                  title={job.title}
                  subtitle={
                    <>
                      {job.company_name} · {formatShift(job.starts_at, job.ends_at)}
                    </>
                  }
                  photoUrl={job.photo_url}
                  category={job.category}
                  aside={
                    <>
                      <span className="text-[17px] leading-6">{brl(job.net_cents)}</span>
                      <Badge tone="success">{job.status_label}</Badge>
                    </>
                  }
                />
              ))}
            </ul>
            {history.length > HISTORY_SIZE && (
              <div className="acoes">
                <Link to="/meus-trabalhos" className="btn btn-secondary">
                  Ver todos
                </Link>
              </div>
            )}
          </>
        )}
      </Card>

      {reviews.length > 0 && (
        <Card>
          <h2>Avaliações recebidas</h2>
          <ul className="m-0 list-none p-0">
            {reviews.map((review) => (
              <li
                key={review.id}
                className="flex flex-col gap-1 border-b border-regua py-4 last:border-b-0"
              >
                <Stars rating={review.rating} />
                {review.comment && <p className="m-0">{review.comment}</p>}
                <span className="text-[13px] leading-5 text-tinta-media">
                  {review.company_name} · {review.vacancy_title}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <DeleteAccountCard />
    </>
  )
}
