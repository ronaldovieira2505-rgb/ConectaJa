import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError, brl, type Vacancy } from '../api'
import { CATEGORIES } from '../categories'
import { Alert, Button, Card, Field, Loading, SelectField } from '../components/ui'

/** Converte "150,50" em centavos; 0 se não for um número válido. */
function toCents(text: string): number {
  const value = Number(text.replace(/\./g, '').replace(',', '.'))
  return Number.isFinite(value) ? Math.round(value * 100) : 0
}

/** Centavos no formato do campo: 10000 → "100,00". */
function fromCents(cents: number): string {
  return (cents / 100).toFixed(2).replace('.', ',')
}

const EMPTY_FORM = {
  title: '',
  category: 'CARGA_DESCARGA',
  description: '',
  street: '',
  number: '',
  complement: '',
  district: '',
  city: '',
  state: '',
  zip_code: '',
  latitude: '',
  longitude: '',
  starts_at: '',
  ends_at: '',
  pay: '',
  positions: '1',
}

/** Formulário preenchido com a vaga original (US25); data e horário ficam vazios. */
function formFrom(source: Vacancy) {
  return {
    ...EMPTY_FORM,
    title: source.title,
    category: source.category,
    description: source.description,
    street: source.street ?? '',
    number: source.number ?? '',
    complement: source.complement ?? '',
    district: source.district ?? '',
    city: source.city ?? '',
    state: source.state ?? '',
    zip_code: source.zip_code ?? '',
    latitude: source.latitude ?? '',
    longitude: source.longitude ?? '',
    pay: fromCents(source.pay_per_person_cents),
    positions: String(source.positions),
  }
}

/** Publicar vaga: cria em AGUARDANDO_PAGAMENTO e leva ao pagamento. */
export default function CompanyVacancyNewPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const duplicateId = searchParams.get('duplicar')
  const [source, setSource] = useState<Vacancy | null>(null)
  const [loadingSource, setLoadingSource] = useState(Boolean(duplicateId))
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState('')
  const [locating, setLocating] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [photo, setPhoto] = useState<File | null>(null)

  useEffect(() => {
    if (!duplicateId) return
    let active = true
    api<Vacancy>(`/api/vacancies/${duplicateId}/`)
      .then((vacancy) => {
        if (!active) return
        setSource(vacancy)
        setForm(formFrom(vacancy))
      })
      .catch(() => active && setError('Não foi possível carregar a vaga para duplicar.'))
      .finally(() => active && setLoadingSource(false))
    return () => {
      active = false
    }
  }, [duplicateId])

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value })

  const perPerson = toCents(form.pay)
  const positions = Number(form.positions) || 0
  const total = perPerson * positions

  function useMyLocation() {
    if (!navigator.geolocation) {
      setError('Seu navegador não permite obter a localização.')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setForm((f) => ({
          ...f,
          latitude: pos.coords.latitude.toFixed(6),
          longitude: pos.coords.longitude.toFixed(6),
        }))
        setLocating(false)
      },
      () => {
        setError('Não foi possível obter sua localização. Informe as coordenadas.')
        setLocating(false)
      },
    )
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (source && (!form.starts_at || !form.ends_at)) {
      setError('Informe a data e o horário do novo turno.')
      return
    }
    setSubmitting(true)
    const toIso = (v: string) => (v ? new Date(v).toISOString() : '')
    try {
      const vacancy = await api<Vacancy>('/api/vacancies/', {
        method: 'POST',
        body: {
          title: form.title,
          category: form.category,
          description: form.description,
          street: form.street,
          number: form.number,
          complement: form.complement,
          district: form.district,
          city: form.city,
          state: form.state,
          zip_code: form.zip_code,
          latitude: form.latitude,
          longitude: form.longitude,
          starts_at: toIso(form.starts_at),
          ends_at: toIso(form.ends_at),
          pay_per_person_cents: perPerson,
          positions,
          ...(source ? { duplicate_of: source.id } : {}),
        },
      })
      if (photo) {
        const upload = new FormData()
        upload.append('photo', photo)
        // A vaga já existe: se a foto falhar, a empresa envia de novo na página da vaga.
        await api(`/api/vacancies/${vacancy.id}/photo/`, { method: 'POST', form: upload }).catch(
          () => undefined,
        )
      }
      navigate(`/empresa/vagas/${vacancy.id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível criar a vaga.')
      setSubmitting(false)
    }
  }

  if (loadingSource) return <Loading rows={1} />

  return (
    <Card>
      <h1>Nova vaga</h1>
      {source && (
        <Alert tone="info">
          Copiamos os dados de “{source.title}”. Escolha a data e o horário do novo turno.
          {source.photo_url && ' A foto da vaga original também será copiada.'}
        </Alert>
      )}
      {error && <Alert tone="error">{error}</Alert>}
      <form onSubmit={onSubmit} noValidate>
        <fieldset className="bloco">
          <legend>O serviço</legend>
          <div className="grade grade-2">
            <Field label="Título" value={form.title} onChange={set('title')} />
            <SelectField label="Categoria" value={form.category} onChange={set('category')}>
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </SelectField>
          </div>
          <Field label="Descrição do escopo" value={form.description} onChange={set('description')} />
        </fieldset>
        <fieldset className="bloco">
          <legend>Onde</legend>
          <div className="grade grade-endereco">
            <Field label="Endereço" value={form.street} onChange={set('street')} />
            <Field label="Número" value={form.number} onChange={set('number')} />
          </div>
          <div className="grade grade-cidade">
            <Field label="Cidade" value={form.city} onChange={set('city')} />
            <Field label="UF" maxLength={2} value={form.state} onChange={set('state')} />
          </div>
          <div className="grade grade-2">
            <Field label="Latitude" value={form.latitude} onChange={set('latitude')} />
            <Field label="Longitude" value={form.longitude} onChange={set('longitude')} />
          </div>
          <p className="sub">As coordenadas definem onde o check-in é aceito.</p>
          <Button type="button" variant="secondary" onClick={useMyLocation} disabled={locating}>
            {locating ? 'Localizando...' : 'Usar minha localização'}
          </Button>
        </fieldset>
        <fieldset className="bloco">
          <legend>Foto do local</legend>
          <Field
            label="Foto (opcional)"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(event) => setPhoto(event.target.files?.[0] ?? null)}
          />
          <p className="sub">JPG, PNG ou WebP, até 5 MB. Aparece na busca e na página da vaga.</p>
        </fieldset>
        <fieldset className="bloco">
          <legend>Quando e quanto</legend>
          <div className="grade grade-2">
            <Field label="Início" type="datetime-local" value={form.starts_at} onChange={set('starts_at')} />
            <Field label="Fim" type="datetime-local" value={form.ends_at} onChange={set('ends_at')} />
          </div>
          <div className="grade grade-2">
            <Field label="Valor por pessoa (R$)" inputMode="decimal" value={form.pay} onChange={set('pay')} />
            <Field label="Número de pessoas" type="number" min={1} value={form.positions} onChange={set('positions')} />
          </div>
        </fieldset>
        <p className="total" aria-live="polite">
          Total a pagar <strong>{brl(total)}</strong>
        </p>
        <Button type="submit" block busy={submitting}>
          Criar vaga
        </Button>
      </form>
    </Card>
  )
}
