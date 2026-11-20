import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  api,
  brl,
  formatDays,
  formatMinutes,
  formatShift,
  ratingLabel,
  type JobItem,
  type VacancyPublicDetail,
  type VacancyRules,
} from '../api'
import CompanyAbout from '../components/CompanyAbout'
import { Alert, Badge, Button, Card, Loading } from '../components/ui'
import VacancyCover from '../components/VacancyCover'
import FavoriteButton from '../components/FavoriteButton'
import ReportLink from '../components/ReportLink'
import EquipmentLists from '../components/EquipmentLists'

/** Detalhe da vaga para o prestador: o essencial à vista e o restante em "ver mais" (US17). */
export default function VacancyPublicDetailPage() {
  const { id } = useParams()
  const [vacancy, setVacancy] = useState<VacancyPublicDetail | null>(null)
  const [error, setError] = useState('')
  const [applying, setApplying] = useState(false)
  const [applyError, setApplyError] = useState('')

  useEffect(() => {
    api<VacancyPublicDetail>(`/api/vacancies/${id}/`)
      .then(setVacancy)
      .catch((err: Error) => setError(err.message))
  }, [id])

  async function handleApply() {
    setApplying(true)
    setApplyError('')
    try {
      const application = await api<JobItem>(`/api/vacancies/${id}/apply/`, {
        method: 'POST',
      })
      setVacancy(
        (current) =>
          current && {
            ...current,
            can_apply: false,
            apply_blocker: 'Você já se candidatou a esta vaga.',
            my_application: {
              id: application.id,
              status: application.status,
              status_label: application.status_label,
            },
          },
      )
    } catch (err) {
      setApplyError((err as Error).message)
    } finally {
      setApplying(false)
    }
  }

  if (error) return <Alert tone="error">{error}</Alert>
  if (!vacancy) return <Loading rows={1} />

  const sent = Boolean(vacancy.my_application)
  const rules = vacancy.rules as VacancyRules | undefined

  const address = [
    [vacancy.street, vacancy.number].filter(Boolean).join(', '),
    vacancy.complement,
    vacancy.district,
    [vacancy.city, vacancy.state].filter(Boolean).join('/'),
  ]
    .filter(Boolean)
    .join(' · ')
  const mapUrl = `https://www.openstreetmap.org/?mlat=${vacancy.latitude}&mlon=${vacancy.longitude}#map=17/${vacancy.latitude}/${vacancy.longitude}`

  const where = [vacancy.district, [vacancy.city, vacancy.state].filter(Boolean).join('/')]
    .filter(Boolean)
    .join(', ')

  return (
    <Card tone={vacancy.payment_guaranteed ? 'carimbo' : undefined}>
      <p>
        <Link to="/vagas">Voltar para a busca</Link>
      </p>
      <VacancyCover
        photoUrl={vacancy.photo_url}
        category={vacancy.category}
        alt="Foto do local do turno"
        className="mb-6 aspect-[16/9] w-full rounded-[24px] md:aspect-[16/7]"
      />
      <div className="flex items-start justify-between gap-3">
        <h1>{vacancy.title}</h1>
        <FavoriteButton
          vacancyId={vacancy.id}
          title={vacancy.title}
          initial={vacancy.favorite ?? false}
          className="shrink-0"
        />
      </div>
      <p className="marcadores">
        <Badge>{vacancy.category_label}</Badge>
        {vacancy.urgent && <Badge tone="warning">Urgente</Badge>}
        {vacancy.payment_guaranteed && <Badge tone="success">Pagamento garantido</Badge>}
      </p>
      <p className="sub">
        {vacancy.company_name} · {ratingLabel(vacancy.company_rating)}
      </p>
      <dl className="fatos">
        <div className="fato-destaque">
          <dt>Você recebe</dt>
          <dd>{brl(vacancy.net_cents)}</dd>
        </div>
        <div>
          <dt>Turno</dt>
          <dd>{formatShift(vacancy.starts_at, vacancy.ends_at)}</dd>
        </div>
        <div>
          <dt>Local</dt>
          <dd>{where}</dd>
        </div>
        <div>
          <dt>Em aberto</dt>
          <dd>
            {vacancy.remaining_positions}{' '}
            {vacancy.remaining_positions === 1 ? 'vaga restante' : 'vagas restantes'}
          </dd>
        </div>
      </dl>
      <div className="acoes">
        <Button disabled={!vacancy.can_apply} busy={applying} onClick={handleApply}>
          {sent ? 'Candidatura enviada' : 'Quero esta vaga'}
        </Button>
      </div>
      {sent && vacancy.my_application?.status === 'PENDENTE' && (
        <Alert tone="success">
          Candidatura enviada! Acompanhe em <Link to="/meus-trabalhos">Meus trabalhos</Link>.
        </Alert>
      )}
      {applyError && <Alert tone="error">{applyError}</Alert>}
      {vacancy.apply_blocker && !applyError && !sent && <Alert>{vacancy.apply_blocker}</Alert>}
      {vacancy.equipment && (
        <EquipmentLists
          bring={vacancy.equipment.bring}
          provided={vacancy.equipment.provided}
          notes={vacancy.equipment.notes}
        />
      )}
      {vacancy.company && (
        <section aria-labelledby="sobre-a-empresa" className="mt-6 border-t border-regua pt-6">
          <h2 id="sobre-a-empresa">Sobre a empresa</h2>
          <CompanyAbout company={vacancy.company} showProfileLink heading="h3" />
        </section>
      )}
      <p className="mt-6">
        <ReportLink
          targetType="VAGA"
          targetId={vacancy.id}
          role="WORKER"
          ariaLabel="Denunciar esta vaga"
        />
      </p>
      <details className="ver-mais">
        <summary>Ver mais sobre a vaga</summary>
        <h2>O serviço</h2>
        <p className="descricao">{vacancy.description}</p>
        <h2>Endereço</h2>
        <p>
          {address}{' '}
          <a href={mapUrl} target="_blank" rel="noreferrer">
            Ver no mapa
          </a>
        </p>
        <h2>Valor</h2>
        <dl className="linhas">
          <div>
            <dt>Valor do turno</dt>
            <dd>{brl(vacancy.gross_cents)}</dd>
          </div>
          <div>
            <dt>Taxa da plataforma ({vacancy.fee_percent}%)</dt>
            <dd>− {brl(vacancy.fee_cents)}</dd>
          </div>
        </dl>
        {rules && (
          <section aria-labelledby="regras-da-vaga">
            <h2 id="regras-da-vaga">Regras desta vaga</h2>
            <ul>
              <li>
                Cancelamento sem penalidade até {formatMinutes(rules.free_cancel_minutes_before)}{' '}
                antes do início; depois disso, {formatDays(rules.late_cancel_block_days)} sem poder
                se candidatar.
              </li>
              <li>
                Check-in pelo celular a até {rules.geofence_radius_m} m do local, a partir de{' '}
                {formatMinutes(rules.checkin_open_minutes_before)} antes do início; sem check-in até{' '}
                {formatMinutes(rules.no_show_tolerance_minutes)} após o início conta como falta.
              </li>
              <li>
                {rules.no_show_limit} {rules.no_show_limit === 1 ? 'falta' : 'faltas'} em{' '}
                {rules.no_show_window_days} dias suspendem a conta por{' '}
                {formatDays(rules.suspension_days)}.
              </li>
              <li>
                Pagamento garantido: o valor já está em custódia. Você recebe{' '}
                {brl(vacancy.net_cents)} (valor do turno menos {vacancy.fee_percent}%) após a
                confirmação das horas, ou automaticamente{' '}
                {formatMinutes(rules.contest_window_minutes)} depois do check-out se a empresa não
                responder.
              </li>
            </ul>
          </section>
        )}
      </details>
    </Card>
  )
}
