import {
  Camera,
  HardHat,
  PartyPopper,
  ShoppingBasket,
  Sparkles,
  Truck,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, brl, formatShift, type VacancyCard } from '../../api'

const PREVIEW_SIZE = 3

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  AJUDANTE_OBRA: HardHat,
  CARGA_DESCARGA: Truck,
  VAREJO: ShoppingBasket,
  EVENTOS: PartyPopper,
  FOTOGRAFIA: Camera,
  LIMPEZA: Sparkles,
}

/** Tons do gradiente da marca, um por posição na grade, para os cartões não ficarem iguais. */
const TILE_TINTS = [
  'bg-[color-mix(in_oklab,var(--gradiente-inicio)_16%,white)]',
  'bg-[color-mix(in_oklab,var(--gradiente-meio)_14%,white)]',
  'bg-[color-mix(in_oklab,var(--gradiente-fim)_16%,white)]',
]

const PILL =
  'inline-flex min-h-8 items-center justify-center rounded-full px-4 text-[13px] leading-4 whitespace-nowrap'

/** Amostra das vagas publicadas agora. Se a busca falhar, a seção simplesmente não aparece. */
export default function OpenVacancies() {
  const [vacancies, setVacancies] = useState<VacancyCard[]>([])

  useEffect(() => {
    let active = true
    api<{ results: VacancyCard[] }>('/api/vacancies/')
      .then((data) => active && setVacancies(data.results))
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [])

  if (vacancies.length === 0) return null

  const count = `${vacancies.length} ${vacancies.length === 1 ? 'vaga aberta' : 'vagas abertas'} agora`

  return (
    <section id="vagas-abertas" aria-labelledby="vagas-abertas-titulo">
      <h2 id="vagas-abertas-titulo" className="sr-only">
        Vagas abertas
      </h2>
      <ul className="m-0 grid list-none grid-cols-1 gap-10 p-0 min-[600px]:max-md:grid-cols-2 min-[600px]:max-md:gap-x-6 md:grid-cols-3 md:gap-coluna">
        {vacancies.slice(0, PREVIEW_SIZE).map((vacancy, index) => {
          const Icon = CATEGORY_ICONS[vacancy.category] ?? Wrench
          return (
            <li key={vacancy.id} className="min-w-0">
              <Link
                to={`/vagas/${vacancy.id}`}
                className="group flex flex-col gap-5 no-underline md:gap-6"
              >
                <span
                  className={`relative grid aspect-[432/360] w-full place-items-center overflow-hidden rounded-cartao ${TILE_TINTS[index % TILE_TINTS.length]}`}
                >
                  <Icon
                    className="size-20 text-tinta/70 transition-transform duration-500 group-hover:scale-110 motion-reduce:transition-none"
                    strokeWidth={0.75}
                    aria-hidden="true"
                  />
                  <span className={`${PILL} absolute top-4 right-4 bg-controle`}>
                    {vacancy.category_label}
                  </span>
                  {vacancy.urgent && (
                    <span className={`${PILL} absolute top-4 left-4 bg-vidro`}>Urgente</span>
                  )}
                </span>
                <span className="flex flex-col items-center gap-2 text-center md:px-4">
                  <span className="text-[15px] leading-6 text-balance">{vacancy.title}</span>
                  <span className="text-[13px] leading-6 text-tinta-media">
                    {formatShift(vacancy.starts_at, vacancy.ends_at)} ·{' '}
                    {vacancy.district ? `${vacancy.district}, ` : ''}
                    {vacancy.city}/{vacancy.state}
                  </span>
                  <span
                    className={`${PILL} bg-controle transition-colors group-hover:bg-[#20202016]`}
                  >
                    Você recebe {brl(vacancy.net_cents)}
                  </span>
                </span>
              </Link>
            </li>
          )
        })}
      </ul>
      <p className="mx-auto mt-10 mb-0 max-w-none text-center text-[13px] text-tinta-media">
        {count} ·{' '}
        <Link to="/vagas" className="text-tinta">
          ver todas
        </Link>
      </p>
    </section>
  )
}
