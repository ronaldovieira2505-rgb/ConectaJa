import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { VacancyCard } from '../../api'
import VacancyTile from '../VacancyTile'

const PREVIEW_SIZE = 6

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
        {vacancies.slice(0, PREVIEW_SIZE).map((vacancy) => (
          <li key={vacancy.id} className="min-w-0">
            <VacancyTile vacancy={vacancy} />
          </li>
        ))}
      </ul>
    </section>
  )
}
