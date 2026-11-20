import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import {
  api,
  ApiError,
  brl,
  formatCnpj,
  formatMonthYear,
  formatShift,
  type CompanyProfile,
  type Vacancy,
  type VacancyList,
} from '../api'
import Avatar from '../components/Avatar'
import HistoryItem from '../components/HistoryItem'
import { Alert, Badge, Button, Card, Loading } from '../components/ui'
import { badgeToneFor } from '../status'
import type { Tone } from '../status'
import PremiumBadge from '../components/PremiumBadge'

const LOGO_TYPES = 'image/jpeg,image/png,image/webp'
const HISTORY_STATUSES = ['FINALIZADA', 'CANCELADA']
const HISTORY_SIZE = 5

const VERIFICATION_TONES: Record<string, 'success' | 'warning' | 'error'> = {
  APROVADA: 'success',
  PENDENTE: 'warning',
  REJEITADA: 'error',
}

const CARD_TONES: Record<string, Tone> = {
  APROVADA: 'carimbo',
  PENDENTE: 'colete',
  REJEITADA: 'encerrada',
}

function addressOf(company: CompanyProfile) {
  return [
    [company.street, company.number].filter(Boolean).join(', '),
    company.complement,
    company.district,
    [company.city, company.state].filter(Boolean).join('/'),
  ]
    .filter(Boolean)
    .join(' · ')
}

/** Perfil da empresa: logo, verificação, números, apresentação, cadastro e histórico de vagas. */
export default function CompanyProfilePage() {
  const [company, setCompany] = useState<CompanyProfile | null>(null)
  const [history, setHistory] = useState<Vacancy[]>([])
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [sendingLogo, setSendingLogo] = useState(false)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [draft, setDraft] = useState({ description: '', phone: '' })

  useEffect(() => {
    api<CompanyProfile>('/api/companies/me/')
      .then(setCompany)
      .catch(() => setError('Não foi possível carregar o perfil da empresa.'))
    api<VacancyList>('/api/company/vacancies/')
      .then((list) => setHistory(list.results.filter((v) => HISTORY_STATUSES.includes(v.status))))
      .catch(() => undefined) // sem histórico, o resto do perfil continua valendo
  }, [])

  async function sendLogo(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = '' // permite escolher o mesmo arquivo de novo
    if (!file) return
    setActionError('')
    setSendingLogo(true)
    const upload = new FormData()
    upload.append('logo', file)
    try {
      setCompany(await api<CompanyProfile>('/api/companies/me/logo/', { method: 'POST', form: upload }))
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Não foi possível enviar a logo.')
    } finally {
      setSendingLogo(false)
    }
  }

  async function removeLogo() {
    setActionError('')
    try {
      setCompany(await api<CompanyProfile>('/api/companies/me/logo/', { method: 'DELETE' }))
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Não foi possível remover a logo.')
    }
  }

  function startEditing(current: CompanyProfile) {
    setDraft({ description: current.description, phone: current.phone })
    setActionError('')
    setEditing(true)
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    setActionError('')
    setSaving(true)
    try {
      setCompany(await api<CompanyProfile>('/api/companies/me/', { method: 'PATCH', body: draft }))
      setEditing(false)
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Não foi possível salvar.')
    } finally {
      setSaving(false)
    }
  }

  if (error) return <Alert tone="error">{error}</Alert>
  if (!company) return <Loading rows={2} />

  const address = addressOf(company)
  const registration: [string, string][] = [
    ['Razão social', company.legal_name],
    ['Nome fantasia', company.trade_name],
    ['CNPJ', formatCnpj(company.cnpj)],
    ['Situação cadastral', company.registration_status],
    ['Regime tributário', company.tax_regime_label],
    ['Inscrição estadual', company.state_registration],
    ['Endereço', address],
    ['Pagamento preferido', company.payment_method_label],
  ]

  return (
    <>
      <Card tone={CARD_TONES[company.verification_status]}>
        <div className="flex flex-wrap items-center gap-5">
          <Avatar src={company.logo_url} name={company.name} kind="company" />
          <div className="flex min-w-[12rem] flex-1 flex-col gap-2">
            <h1 className="m-0">{company.name}</h1>
            <p className="marcadores m-0">
              <Badge tone={VERIFICATION_TONES[company.verification_status] ?? 'warning'}>
                {company.verification_status === 'APROVADA'
                  ? 'Empresa verificada'
                  : `Cadastro: ${company.verification_label.toLowerCase()}`}
              </Badge>
              <Badge>Desde {formatMonthYear(company.member_since)}</Badge>
            </p>
            <p className="sub m-0">CNPJ {formatCnpj(company.cnpj)}</p>
          </div>
        </div>
        <div className="acoes">
          <label className={`btn btn-secondary ${sendingLogo ? 'btn-busy' : ''}`}>
            {company.logo_url ? 'Trocar logo' : 'Enviar logo'}
            <input
              type="file"
              accept={LOGO_TYPES}
              className="sr-only"
              disabled={sendingLogo}
              onChange={sendLogo}
            />
          </label>
          {company.logo_url && (
            <Button variant="secondary" onClick={removeLogo}>
              Remover logo
            </Button>
          )}
        </div>
        {actionError && <Alert tone="error">{actionError}</Alert>}
        <dl className="fatos">
          <div className="fato-destaque">
            <dt>Vagas publicadas</dt>
            <dd>{company.stats.published_vacancies}</dd>
          </div>
          <div className="fato-destaque">
            <dt>Turnos concluídos</dt>
            <dd>{company.stats.completed_shifts}</dd>
          </div>
          <div className="fato-destaque">
            <dt>Total pago</dt>
            <dd>{brl(company.stats.total_paid_cents)}</dd>
          </div>
        </dl>
      </Card>

      {company.premium && (
        <Card>
          <h2>Contratante premium</h2>
          {company.premium.active ? (
            <>
              <p>
                <PremiumBadge />
              </p>
              <p>Sua empresa tem o selo. Ele aparece ao lado do nome na busca e no detalhe das vagas.</p>
            </>
          ) : (
            <>
              <p>Sua empresa ainda não tem o selo. Falta:</p>
              <ul aria-label="O que falta para o selo">
                {company.premium.missing.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          <p className="sub">{company.premium.explanation}</p>
        </Card>
      )}

      <Card>
        <h2>Sobre a empresa</h2>
        {editing ? (
          <form onSubmit={save} noValidate>
            <div className="field">
              <label htmlFor="empresa-descricao">Apresentação</label>
              <textarea
                id="empresa-descricao"
                rows={4}
                maxLength={1000}
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="empresa-telefone">Telefone</label>
              <input
                id="empresa-telefone"
                type="tel"
                maxLength={20}
                value={draft.phone}
                onChange={(e) => setDraft({ ...draft, phone: e.target.value })}
              />
            </div>
            <div className="acoes">
              <Button type="submit" busy={saving}>
                Salvar
              </Button>
              <Button type="button" variant="secondary" onClick={() => setEditing(false)}>
                Cancelar
              </Button>
            </div>
          </form>
        ) : (
          <>
            <p className={company.description ? 'descricao' : 'sub'}>
              {company.description || 'Conte aos prestadores o que a empresa faz.'}
            </p>
            {company.phone && <p className="sub">Telefone {company.phone}</p>}
            <div className="acoes">
              <Button variant="secondary" onClick={() => startEditing(company)}>
                Editar apresentação
              </Button>
            </div>
          </>
        )}
      </Card>

      <Card>
        <h2>Dados cadastrais</h2>
        <dl className="linhas">
          {registration
            .filter(([, value]) => value)
            .map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
        </dl>
      </Card>

      <Card>
        <h2>Histórico de vagas</h2>
        {history.length === 0 ? (
          <div className="vazio">
            <p>Nenhuma vaga encerrada ainda.</p>
            <Link to="/empresa/vagas" className="btn btn-primary">
              Ver minhas vagas
            </Link>
          </div>
        ) : (
          <>
            <ul className="m-0 list-none p-0">
              {history.slice(0, HISTORY_SIZE).map((vacancy) => (
                <HistoryItem
                  key={vacancy.id}
                  to={`/empresa/vagas/${vacancy.id}`}
                  title={vacancy.title}
                  subtitle={
                    <>
                      {formatShift(vacancy.starts_at, vacancy.ends_at)} · {vacancy.positions}{' '}
                      {vacancy.positions === 1 ? 'posição' : 'posições'}
                    </>
                  }
                  photoUrl={vacancy.photo_url}
                  category={vacancy.category}
                  aside={
                    <>
                      <span className="text-[17px] leading-6">{brl(vacancy.total_cents)}</span>
                      <Badge tone={badgeToneFor(vacancy.status)}>{vacancy.status_label}</Badge>
                    </>
                  }
                />
              ))}
            </ul>
            {history.length > HISTORY_SIZE && (
              <div className="acoes">
                <Link to="/empresa/vagas" className="btn btn-secondary">
                  Ver todas
                </Link>
              </div>
            )}
          </>
        )}
      </Card>
    </>
  )
}
