import { ArrowRight, CalendarClock, MapPin } from 'lucide-react'
import { Link } from 'react-router-dom'
import { brl, formatShift, type VacancyCard } from '../../api'
import { categoryIcon } from './categoryIcons'

const PREVIEW_SIZE = 6

const META = 'flex items-center gap-2 text-[13px] leading-5 text-tinta-media'
const META_ICON = 'size-4 shrink-0'

function place(vacancy: VacancyCard) {
  return `${vacancy.district ? `${vacancy.district}, ` : ''}${vacancy.city}/${vacancy.state}`
}

/** Vitrine das vagas publicadas agora. Sem vagas, a seção não aparece. */
export default function OpenVacancies({ vacancies }: { vacancies: VacancyCard[] }) {
  if (vacancies.length === 0) return null

  const count = `${vacancies.length} ${vacancies.length === 1 ? 'vaga aberta' : 'vagas abertas'} agora`

  return (
    <section id="vagas-abertas" aria-labelledby="vagas-abertas-titulo">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div>
          <h2 id="vagas-abertas-titulo" className="m-0 text-[22px] leading-7">
            Vagas abertas
          </h2>
          <p className="m-0 text-[13px] leading-5 text-tinta-media">{count}</p>
        </div>
        <Link to="/vagas" className="btn btn-secondary group gap-3">
          Ver todas
          <ArrowRight
            className="size-4 transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
            strokeWidth={1.25}
            aria-hidden="true"
          />
        </Link>
      </div>
      <ul className="m-0 grid list-none grid-cols-1 gap-4 p-0 min-[600px]:grid-cols-2 xl:grid-cols-3">
        {vacancies.slice(0, PREVIEW_SIZE).map((vacancy) => {
          const Icon = categoryIcon(vacancy.category)
          return (
            <li key={vacancy.id} className="min-w-0">
              <Link
                to={`/vagas/${vacancy.id}`}
                className="group flex h-full flex-col gap-4 rounded-[24px] border border-regua bg-papel p-5 no-underline transition-shadow hover:shadow-[0_8px_24px_rgb(32_32_32/8%)] motion-reduce:transition-none"
              >
                <span className="flex items-center gap-3">
                  <span className="grid size-10 shrink-0 place-items-center rounded-full bg-ficha">
                    <Icon className="size-5" strokeWidth={1.25} aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[13px] leading-4 text-tinta-media">
                    {vacancy.category_label}
                  </span>
                  {vacancy.urgent && <span className="badge badge-warning">Urgente</span>}
                </span>
                <span className="flex flex-col gap-1">
                  <span className="text-[17px] leading-6 text-balance">{vacancy.title}</span>
                  <span className="text-[13px] leading-5 text-tinta-media">
                    {vacancy.company_name}
                  </span>
                </span>
                <span className="flex flex-col gap-1.5">
                  <span className={META}>
                    <CalendarClock className={META_ICON} strokeWidth={1.25} aria-hidden="true" />
                    {formatShift(vacancy.starts_at, vacancy.ends_at)}
                  </span>
                  <span className={META}>
                    <MapPin className={META_ICON} strokeWidth={1.25} aria-hidden="true" />
                    {place(vacancy)}
                  </span>
                </span>
                <span className="mt-auto flex items-end justify-between gap-3 border-t border-regua pt-4">
                  <span className="flex flex-col">
                    <span className="text-[12px] leading-4 text-tinta-media">Você recebe</span>
                    <span className="text-[22px] leading-7">{brl(vacancy.net_cents)}</span>
                  </span>
                  <span className="text-[12px] leading-4 text-tinta-media">
                    {vacancy.remaining_positions}{' '}
                    {vacancy.remaining_positions === 1 ? 'posição' : 'posições'}
                  </span>
                </span>
              </Link>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
