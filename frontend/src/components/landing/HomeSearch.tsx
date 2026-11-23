import { BadgeCheck, MapPin, Search, ShieldCheck, Wallet } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { brl, type VacancyCard } from '../../api'
import { CATEGORIES } from '../../categories'
import { categoryColor, categoryGradient } from '../../categoryColors'
import CategoryIcon from '../CategoryIcon'

/** Atalhos logo abaixo da busca: as categorias com mais chance de ter turno hoje. */
const QUICK = ['LIMPEZA', 'CARGA_DESCARGA', 'EVENTOS', 'VAREJO']

/** Vaga do mostruário quando a busca ainda não respondeu ou não há vagas abertas. */
const SAMPLE = {
  title: 'Repositor de gôndolas',
  category: 'VAREJO',
  category_label: 'Varejo',
  place: 'Mooca, São Paulo',
  net_cents: 13095,
}

const GLASS =
  'rounded-[20px] bg-white/85 shadow-[0_18px_40px_rgb(32_32_32/16%)] backdrop-blur-flutuante'

function Showcase({ vacancy }: { vacancy?: VacancyCard }) {
  const shown = vacancy
    ? {
        title: vacancy.title,
        category: vacancy.category,
        category_label: vacancy.category_label,
        place: [vacancy.district, vacancy.city].filter(Boolean).join(', '),
        net_cents: vacancy.net_cents,
      }
    : SAMPLE
  return (
    // Ilustração: mostra como o turno anda no app. Os leitores de tela pulam esta parte.
    <div className="relative mx-auto h-[360px] w-full max-w-[420px]" aria-hidden="true">
      <div className={`${GLASS} absolute top-6 left-4 w-[78%] overflow-hidden motion-safe:animate-flutua`}>
        <div
          className="grid h-28 place-items-center"
          style={{ backgroundImage: categoryGradient(shown.category) }}
        >
          <CategoryIcon category={shown.category} className="size-12 text-white" strokeWidth={1.2} />
        </div>
        <div className="flex flex-col gap-1 p-4 text-left">
          <span className="text-[12px] leading-4" style={{ color: categoryColor(shown.category).ink }}>
            {shown.category_label}
          </span>
          <span className="truncate text-[15px] leading-5">{shown.title}</span>
          <span className="flex items-center gap-1 text-[12px] leading-4 text-tinta-media">
            <MapPin className="size-3.5" strokeWidth={1.5} />
            <span className="truncate">{shown.place}</span>
          </span>
          <span className="mt-2 flex items-baseline justify-between gap-2 border-t border-regua pt-2">
            <span className="text-[12px] text-tinta-media">Você recebe</span>
            <span className="text-[20px] leading-6">{brl(shown.net_cents)}</span>
          </span>
        </div>
      </div>

      <div
        className={`${GLASS} absolute top-2 right-0 flex items-center gap-2 px-3 py-2 text-[12px] motion-safe:animate-flutua [animation-delay:-2s]`}
      >
        <span className="grid size-7 place-items-center rounded-full bg-[#E3F7F0] text-[#0B6B5D]">
          <ShieldCheck className="size-4" strokeWidth={1.75} />
        </span>
        Pagamento retido
      </div>

      <div
        className={`${GLASS} absolute right-0 bottom-4 flex items-center gap-2 px-3 py-2 text-[12px] motion-safe:animate-flutua [animation-delay:-4s]`}
      >
        <span className="grid size-7 place-items-center rounded-full bg-[#E8F0FF] text-[#2C3FA6]">
          <MapPin className="size-4" strokeWidth={1.75} />
        </span>
        <span className="flex flex-col leading-4">
          Check-in confirmado
          <span className="text-tinta-media">no local do turno</span>
        </span>
      </div>

      <div
        className={`${GLASS} absolute bottom-4 left-0 flex items-center gap-3 px-4 py-3 text-[12px] motion-safe:animate-flutua [animation-delay:-1s]`}
      >
        <span className="grid size-9 place-items-center rounded-full bg-[#10B981] text-white">
          <Wallet className="size-5" strokeWidth={1.75} />
        </span>
        <span className="flex flex-col leading-4">
          <span className="text-tinta-media">PIX recebido</span>
          <span className="text-[16px] leading-5">+ {brl(shown.net_cents)}</span>
        </span>
      </div>
    </div>
  )
}

/** Abertura da página inicial: a busca de vagas é a primeira ação, com o turno ilustrado ao lado. */
export default function HomeSearch({ vacancies = [] }: { vacancies?: VacancyCard[] }) {
  const [term, setTerm] = useState('')
  const navigate = useNavigate()

  function submit(event: FormEvent) {
    event.preventDefault()
    const q = term.trim()
    navigate(q ? `/vagas?q=${encodeURIComponent(q)}` : '/vagas')
  }

  return (
    <section
      aria-labelledby="busca-titulo"
      className="superficie-gradiente grid items-center gap-8 overflow-hidden rounded-cartao px-5 py-10 md:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] md:px-12 md:py-14 motion-safe:animate-sobe"
    >
      <div className="flex flex-col items-center gap-6 text-center md:items-start md:text-left">
        <span className="inline-flex items-center gap-2 rounded-full bg-white/80 px-3 py-1.5 text-[12px] leading-4 backdrop-blur-flutuante">
          <BadgeCheck className="size-4 text-[#8C5DC0]" strokeWidth={1.75} aria-hidden="true" />
          Turnos curtos com pagamento garantido
        </span>
        <h1
          id="busca-titulo"
          className="m-0 text-[32px] leading-10 text-balance md:text-[48px] md:leading-[56px]"
        >
          Que turno você procura?
        </h1>
        <form
          role="search"
          onSubmit={submit}
          className="flex w-full max-w-[560px] items-center gap-2 rounded-full bg-papel py-1.5 pr-1.5 pl-5 shadow-[0_12px_32px_rgb(32_32_32/14%)] focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-foco"
        >
          <Search className="size-5 shrink-0 text-tinta-media" strokeWidth={1.5} aria-hidden="true" />
          <input
            type="search"
            aria-label="Buscar vagas"
            placeholder="Ex.: limpeza, carga, eventos"
            value={term}
            onChange={(event) => setTerm(event.target.value)}
            className="h-11 min-w-0 flex-1 border-0 bg-transparent font-texto text-[15px] text-tinta outline-none placeholder:text-tinta-media"
          />
          <button type="submit" className="btn btn-primary">
            Buscar
          </button>
        </form>
        <ul className="m-0 flex list-none flex-wrap justify-center gap-2 p-0 md:justify-start">
          {QUICK.map((value) => {
            const label = CATEGORIES.find((c) => c.value === value)?.label ?? value
            return (
              <li key={value}>
                <Link
                  to={`/vagas?category=${value}`}
                  aria-label={`Buscar vagas de ${label}`}
                  className="inline-flex items-center gap-1.5 rounded-full bg-white/80 py-1.5 pr-3 pl-1.5 text-[12px] leading-4 no-underline backdrop-blur-flutuante transition-colors hover:bg-white"
                >
                  <span
                    className="grid size-6 place-items-center rounded-full text-white"
                    style={{ backgroundImage: categoryGradient(value) }}
                  >
                    <CategoryIcon category={value} className="size-3.5" strokeWidth={1.75} />
                  </span>
                  {label}
                </Link>
              </li>
            )
          })}
        </ul>
        <p className="m-0 max-w-none text-[13px] leading-5">
          É empresa? <Link to="/cadastro/empresa">Publique um turno</Link>
        </p>
      </div>
      <div className="hidden md:block">
        <Showcase vacancy={vacancies[0]} />
      </div>
    </section>
  )
}
