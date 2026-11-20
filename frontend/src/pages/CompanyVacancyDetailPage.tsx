import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, brl, formatShift, type Vacancy } from '../api'
import { CATEGORIES } from '../categories'
import CancelReasonForm from '../components/CancelReasonForm'
import EquipmentFields from '../components/EquipmentFields'
import EquipmentLists from '../components/EquipmentLists'
import { Alert, Badge, Button, Card, Field, Loading, SelectField, Slots } from '../components/ui'
import VacancyCover from '../components/VacancyCover'
import { equipmentLabel, type EquipmentEntry } from '../equipment'
import { badgeToneFor, toneFor } from '../status'
import PendingAssignmentsSection from './PendingAssignments'
import VacancyCandidatesSection from './VacancyCandidates'

const METHODS: Record<string, string> = { PIX: 'PIX', BOLETO: 'boleto', CARTAO: 'cartão' }
const PHOTO_TYPES = 'image/jpeg,image/png,image/webp'
const READ_ONLY_HINT =
  'Para alterar valor ou número de pessoas, remova o anúncio (estorno total) e publique um novo.'

/** Converte um ISO UTC no valor de um input datetime-local (horário local). */
function toLocalInput(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Detalhe da vaga; aguardando pagamento mostra "Pagar e publicar" (PSP simulado). */
export default function CompanyVacancyDetailPage() {
  const { id } = useParams()
  const [vacancy, setVacancy] = useState<Vacancy | null>(null)
  const [error, setError] = useState('')
  const [paid, setPaid] = useState(false)
  const [paying, setPaying] = useState(false)
  const [saved, setSaved] = useState(false)
  const [editing, setEditing] = useState(false)
  const [confirmingRemove, setConfirmingRemove] = useState(false)
  const [removed, setRemoved] = useState(false)
  const [confirmingCancel, setConfirmingCancel] = useState(false)
  const [cancelled, setCancelled] = useState(false)
  const [sendingPhoto, setSendingPhoto] = useState(false)
  const [form, setForm] = useState({
    title: '',
    category: '',
    description: '',
    street: '',
    city: '',
    state: '',
    latitude: '',
    longitude: '',
    starts_at: '',
    ends_at: '',
  })
  const [equipment, setEquipment] = useState<EquipmentEntry[]>([])
  const [equipmentNotes, setEquipmentNotes] = useState('')

  useEffect(() => {
    api<Vacancy>(`/api/vacancies/${id}/`)
      .then(setVacancy)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Não foi possível carregar a vaga.'))
  }, [id])

  function refreshVacancy() {
    api<Vacancy>(`/api/vacancies/${id}/`)
      .then(setVacancy)
      .catch(() => undefined)
  }

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value })

  async function pay() {
    setError('')
    setPaying(true)
    try {
      setVacancy(await api<Vacancy>(`/api/vacancies/${id}/pay/`, { method: 'POST' }))
      setPaid(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível concluir o pagamento.')
    } finally {
      setPaying(false)
    }
  }

  async function sendPhoto(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = '' // permite escolher o mesmo arquivo de novo
    if (!file) return
    setError('')
    setSendingPhoto(true)
    const upload = new FormData()
    upload.append('photo', file)
    try {
      setVacancy(
        await api<Vacancy>(`/api/vacancies/${id}/photo/`, { method: 'POST', form: upload }),
      )
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível enviar a foto.')
    } finally {
      setSendingPhoto(false)
    }
  }

  async function removePhoto() {
    setError('')
    try {
      setVacancy(await api<Vacancy>(`/api/vacancies/${id}/photo/`, { method: 'DELETE' }))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível remover a foto.')
    }
  }

  function startEditing(v: Vacancy) {
    setForm({
      title: v.title,
      category: v.category,
      description: v.description,
      street: v.street ?? '',
      city: v.city ?? '',
      state: v.state ?? '',
      latitude: v.latitude ?? '',
      longitude: v.longitude ?? '',
      starts_at: toLocalInput(v.starts_at),
      ends_at: toLocalInput(v.ends_at),
    })
    setEquipment(v.equipment ?? [])
    setEquipmentNotes(v.equipment_notes ?? '')
    setError('')
    setSaved(false)
    setConfirmingRemove(false)
    setEditing(true)
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    setError('')
    try {
      setVacancy(
        await api<Vacancy>(`/api/vacancies/${id}/`, {
          method: 'PATCH',
          body: {
            ...form,
            starts_at: new Date(form.starts_at).toISOString(),
            ends_at: new Date(form.ends_at).toISOString(),
            equipment,
            equipment_notes: equipmentNotes,
          },
        }),
      )
      setEditing(false)
      setSaved(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível salvar as alterações.')
    }
  }

  async function remove() {
    setError('')
    try {
      setVacancy(await api<Vacancy>(`/api/vacancies/${id}/remove/`, { method: 'POST' }))
      setRemoved(true)
      setEditing(false)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível remover o anúncio.')
    } finally {
      setConfirmingRemove(false)
    }
  }

  async function cancelWhole(reason: string) {
    setError('')
    try {
      setVacancy(
        await api<Vacancy>(`/api/vacancies/${id}/cancel/`, { method: 'POST', body: { reason } }),
      )
      setCancelled(true)
      setConfirmingCancel(false)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível cancelar a vaga.')
    }
  }

  if (!vacancy && !error) return <Loading rows={1} />

  return (
    <Card tone={vacancy ? toneFor(vacancy.status) : undefined}>
      {error && <Alert tone="error">{error}</Alert>}
      {paid && <Alert tone="success">Pagamento confirmado. A vaga foi publicada.</Alert>}
      {saved && <Alert tone="success">Alterações salvas.</Alert>}
      {removed && <Alert tone="success">Anúncio removido. O valor foi estornado.</Alert>}
      {cancelled && (
        <Alert tone="success">
          Vaga cancelada. O valor foi estornado e os prestadores foram avisados.
        </Alert>
      )}
      {vacancy && editing && (
        <form onSubmit={save} noValidate>
          <h1>Editar vaga</h1>
          <Field label="Título" value={form.title} onChange={set('title')} />
          <SelectField label="Categoria" value={form.category} onChange={set('category')}>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </SelectField>
          <Field label="Descrição do escopo" value={form.description} onChange={set('description')} />
          <Field label="Endereço" value={form.street} onChange={set('street')} />
          <Field label="Cidade" value={form.city} onChange={set('city')} />
          <Field label="UF" maxLength={2} value={form.state} onChange={set('state')} />
          <Field label="Latitude" value={form.latitude} onChange={set('latitude')} />
          <Field label="Longitude" value={form.longitude} onChange={set('longitude')} />
          <Field label="Início" type="datetime-local" value={form.starts_at} onChange={set('starts_at')} />
          <Field label="Fim" type="datetime-local" value={form.ends_at} onChange={set('ends_at')} />
          <EquipmentFields
            value={equipment}
            notes={equipmentNotes}
            onChange={setEquipment}
            onNotesChange={setEquipmentNotes}
          />
          <Field label="Valor por pessoa" value={brl(vacancy.pay_per_person_cents)} readOnly />
          <Field label="Número de pessoas" value={String(vacancy.positions)} readOnly />
          <p>{READ_ONLY_HINT}</p>
          <Button type="submit">Salvar alterações</Button>{' '}
          <Button type="button" variant="secondary" onClick={() => setEditing(false)}>
            Cancelar
          </Button>
        </form>
      )}
      {vacancy && !editing && (
        <>
          <VacancyCover
            photoUrl={vacancy.photo_url}
            category={vacancy.category}
            alt="Foto do local do turno"
            className="mb-4 aspect-[16/9] w-full rounded-[24px] md:aspect-[16/7]"
          />
          {!['FINALIZADA', 'CANCELADA'].includes(vacancy.status) && (
            <div className="acoes">
              <label className={`btn btn-secondary ${sendingPhoto ? 'btn-busy' : ''}`}>
                {vacancy.photo_url ? 'Trocar foto do local' : 'Enviar foto do local'}
                <input
                  type="file"
                  accept={PHOTO_TYPES}
                  className="sr-only"
                  disabled={sendingPhoto}
                  onChange={sendPhoto}
                />
              </label>
              {vacancy.photo_url && (
                <Button variant="secondary" onClick={removePhoto}>
                  Remover foto
                </Button>
              )}
            </div>
          )}
          <h1>{vacancy.title}</h1>
          <p className="marcadores">
            <Badge tone={badgeToneFor(vacancy.status)}>{vacancy.status_label}</Badge>
            <Badge>{vacancy.category_label}</Badge>
          </p>
          {/* Duplicar (US25): abre "Nova vaga" preenchida; nada é criado até confirmar. */}
          <div className="acoes">
            <Link to={`/empresa/vagas/nova?duplicar=${vacancy.id}`} className="btn btn-secondary">
              Duplicar
            </Link>
          </div>
          <dl className="fatos">
            <div className="fato-destaque">
              <dt>Total a pagar</dt>
              <dd>{brl(vacancy.total_cents)}</dd>
            </div>
            <div>
              <dt>Valor por pessoa</dt>
              <dd>{brl(vacancy.pay_per_person_cents)}</dd>
            </div>
            <div>
              <dt>Turno</dt>
              <dd>{formatShift(vacancy.starts_at, vacancy.ends_at)}</dd>
            </div>
            <div>
              <dt>Posições</dt>
              <dd>
                <Slots filled={vacancy.filled_positions} total={vacancy.positions} />
              </dd>
            </div>
            {vacancy.retained_cents > 0 && (
              <div>
                <dt>Retido em custódia</dt>
                <dd>{brl(vacancy.retained_cents)}</dd>
              </div>
            )}
          </dl>
          <details className="ver-mais">
            <summary>Ver mais sobre a vaga</summary>
            <h2>O serviço</h2>
            <p className="descricao">{vacancy.description}</p>
            {(vacancy.street || vacancy.city) && (
              <>
                <h2>Endereço</h2>
                <p>
                  {[vacancy.street, [vacancy.city, vacancy.state].filter(Boolean).join('/')]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
              </>
            )}
            <EquipmentLists
              bring={(vacancy.equipment ?? [])
                .filter((e) => e.provider === 'PRESTADOR')
                .map((e) => equipmentLabel(e.item))}
              provided={(vacancy.equipment ?? [])
                .filter((e) => e.provider === 'EMPRESA')
                .map((e) => equipmentLabel(e.item))}
              notes={vacancy.equipment_notes ?? ''}
            />
          </details>
          {['PUBLICADA', 'CANDIDATURAS_ENCERRADAS', 'EM_ANDAMENTO'].includes(vacancy.status) && (
            <VacancyCandidatesSection vacancyId={vacancy.id} onChange={refreshVacancy} />
          )}
          {['CANDIDATURAS_ENCERRADAS', 'EM_ANDAMENTO'].includes(vacancy.status) && (
            <PendingAssignmentsSection vacancyId={vacancy.id} onChange={refreshVacancy} />
          )}
          {vacancy.status === 'AGUARDANDO_PAGAMENTO' && (
            <>
              {vacancy.payment_method && (
                <p className="sub">
                  Cobramos pelo meio que você escolheu no cadastro:{' '}
                  {METHODS[vacancy.payment_method] ?? vacancy.payment_method}.
                </p>
              )}
              <div className="acoes">
                <Button onClick={pay} busy={paying}>
                  Pagar e publicar
                </Button>
              </div>
            </>
          )}
          {['PUBLICADA', 'CANDIDATURAS_ENCERRADAS'].includes(vacancy.status) &&
            vacancy.filled_positions > 0 &&
            (!confirmingCancel ? (
              <div className="acoes">
                <Button variant="secondary" onClick={() => setConfirmingCancel(true)}>
                  Cancelar vaga inteira
                </Button>
              </div>
            ) : (
              <Alert tone="info">
                <p>
                  Cancelar a vaga inteira cancela todos os turnos confirmados, expira as candidaturas
                  pendentes, estorna o valor integral e avisa todos os prestadores.
                </p>
                <CancelReasonForm
                  confirmLabel="Confirmar cancelamento da vaga"
                  onConfirm={cancelWhole}
                  onBack={() => setConfirmingCancel(false)}
                />
              </Alert>
            ))}
          {vacancy.status === 'PUBLICADA' && (
            <>
              {!confirmingRemove ? (
                <div className="acoes">
                  <Button variant="secondary" onClick={() => startEditing(vacancy)}>
                    Editar
                  </Button>
                  <Button variant="secondary" onClick={() => setConfirmingRemove(true)}>
                    Remover anúncio
                  </Button>
                </div>
              ) : (
                <Alert tone="info">
                  <p>Remover o anúncio estorna o valor integral e expira as candidaturas pendentes.</p>
                  <div className="acoes">
                    <Button onClick={remove}>Confirmar remoção</Button>
                    <Button variant="secondary" onClick={() => setConfirmingRemove(false)}>
                      Voltar
                    </Button>
                  </div>
                </Alert>
              )}
            </>
          )}
        </>
      )}
    </Card>
  )
}
