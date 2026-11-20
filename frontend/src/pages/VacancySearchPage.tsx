import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type VacancyCard } from '../api'
import { CATEGORIES } from '../categories'
import { Alert, Button, Card, Field, Loading, SelectField } from '../components/ui'
import VacancyTile from '../components/VacancyTile'

interface Filters {
  q: string
  category: string
  date_from: string
  date_to: string
  min_pay: string
  // "Só nos meus horários" (US10): '1' ligado, '' desligado.
  my_schedule: string
}

const EMPTY: Filters = {
  q: '',
  category: '',
  date_from: '',
  date_to: '',
  min_pay: '',
  my_schedule: '',
}

/** Filtros que chegam pelo endereço (busca e categorias da página inicial). */
function filtersFromUrl(params: URLSearchParams): Filters {
  const category = params.get('category') ?? ''
  return {
    ...EMPTY,
    q: params.get('q') ?? '',
    category: CATEGORIES.some((c) => c.value === category) ? category : '',
  }
}

type Origin = { lat: number; lng: number } | null

function buildQuery(filters: Filters, origin: Origin): string {
  const params = new URLSearchParams()
  if (filters.q.trim()) params.set('q', filters.q.trim())
  if (filters.category) params.set('category', filters.category)
  if (filters.date_from) params.set('date_from', filters.date_from)
  if (filters.date_to) params.set('date_to', filters.date_to)
  if (filters.min_pay) params.set('min_pay', String(Math.round(Number(filters.min_pay) * 100)))
  if (filters.my_schedule) params.set('my_schedule', '1')
  if (origin) {
    params.set('lat', origin.lat.toFixed(6))
    params.set('lng', origin.lng.toFixed(6))
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

/** Buscar vagas: texto, filtros (US13), proximidade (US14) e valor líquido (US17). */
export default function VacancySearchPage() {
  const [searchParams] = useSearchParams()
  const [initial] = useState(() => filtersFromUrl(searchParams))
  const [draft, setDraft] = useState<Filters>(initial)
  const [filters, setFilters] = useState<Filters>(initial)
  const [origin, setOrigin] = useState<Origin>(null)
  const [results, setResults] = useState<VacancyCard[] | null>(null)
  const [error, setError] = useState('')
  // Consulta cujo resultado está na tela; se for diferente da atual, a busca está atualizando.
  const [loadedQuery, setLoadedQuery] = useState<string | null>(null)
  const [showFilters, setShowFilters] = useState(false)
  // O servidor diz se o prestador logado marcou disponibilidade (US10).
  const [scheduleAvailable, setScheduleAvailable] = useState(false)

  useEffect(() => {
    if (!('geolocation' in navigator)) return
    navigator.geolocation.getCurrentPosition(
      (pos) => setOrigin({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => undefined, // sem permissão: ordena por data de início
    )
  }, [])

  const query = buildQuery(filters, origin)
  const loading = loadedQuery !== query

  useEffect(() => {
    let active = true
    api<{ results: VacancyCard[]; my_schedule_available?: boolean }>(`/api/vacancies/${query}`)
      .then((data) => {
        if (!active) return
        setResults(data.results)
        setScheduleAvailable(Boolean(data.my_schedule_available))
        setError('')
      })
      .catch((err: Error) => active && setError(err.message))
      .finally(() => active && setLoadedQuery(query))
    return () => {
      active = false
    }
  }, [query])

  function submit(event: FormEvent) {
    event.preventDefault()
    setFilters(draft)
  }

  function clear() {
    setDraft(EMPTY)
    setFilters(EMPTY)
  }

  // Filtros além do texto: no celular ficam recolhidos e o botão mostra quantos estão ativos.
  const activeExtras = [
    filters.category,
    filters.date_from,
    filters.date_to,
    filters.min_pay,
    filters.my_schedule,
  ].filter(Boolean).length

  const hasAnyFilter = [draft, filters].some((f) => Object.values(f).some(Boolean))

  const set = (name: keyof Filters) => (e: { target: { value: string } }) =>
    setDraft({ ...draft, [name]: e.target.value })

  return (
    <>
      <Card tone="colete">
        <h1>Buscar vagas</h1>
        <form onSubmit={submit} role="search">
          <div className="filtros">
            <Field
              label="Buscar"
              type="search"
              value={draft.q}
              onChange={set('q')}
              placeholder="Ex.: limpeza, carga"
            />
            <div className={`filtros-extra ${showFilters ? 'aberto' : ''}`} id="filtros-extra">
              <SelectField label="Categoria" value={draft.category} onChange={set('category')}>
                <option value="">Todas</option>
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </SelectField>
              <Field label="De" type="date" value={draft.date_from} onChange={set('date_from')} />
              <Field label="Até" type="date" value={draft.date_to} onChange={set('date_to')} />
              <Field
                label="Receber no mínimo (R$)"
                type="number"
                min="0"
                step="1"
                value={draft.min_pay}
                onChange={set('min_pay')}
              />
              {scheduleAvailable && (
                <label className="self-end">
                  <input
                    type="checkbox"
                    checked={draft.my_schedule === '1'}
                    onChange={(e) => setDraft({ ...draft, my_schedule: e.target.checked ? '1' : '' })}
                  />{' '}
                  Só nos meus horários
                </label>
              )}
            </div>
          </div>
          <div className="acoes">
            <Button type="submit" busy={loading && results !== null}>
              Buscar
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="so-celular"
              aria-expanded={showFilters}
              aria-controls="filtros-extra"
              onClick={() => setShowFilters((v) => !v)}
            >
              {showFilters ? 'Menos filtros' : `Filtros${activeExtras ? ` (${activeExtras})` : ''}`}
            </Button>
            {hasAnyFilter && (
              <Button type="button" variant="secondary" onClick={clear}>
                Limpar filtros
              </Button>
            )}
          </div>
        </form>
        <p className="sub">
          {origin ? 'Mais próximas primeiro.' : 'Ordenadas pela data de início.'}
        </p>
      </Card>

      {error && <Alert tone="error">{error}</Alert>}
      {!results && !error && <Loading />}
      {results && results.length === 0 && (
        <Card>
          <div className="vazio">
            <h2>Nenhuma vaga com esses filtros</h2>
            <p>Amplie o período, baixe o valor mínimo ou limpe os filtros.</p>
          </div>
        </Card>
      )}
      {results && results.length > 0 && (
        <ul
          className="resultados m-0 mt-6 grid list-none grid-cols-1 gap-4 p-0 min-[600px]:grid-cols-2 min-[900px]:grid-cols-3"
          aria-busy={loading}
          data-atualizando={loading || undefined}
        >
          {results.map((v) => (
            <li key={v.id} className="min-w-0">
              <VacancyTile vacancy={v} heading="h2" />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
