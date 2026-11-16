import { Link } from 'react-router-dom'
import type { VacancyCard } from '../../api'
import { CATEGORIES } from '../../categories'
import CategoryIcon from '../CategoryIcon'

/** Atalhos para a busca já filtrada por categoria, com a contagem das vagas abertas. */
export default function CategoryGrid({ vacancies }: { vacancies: VacancyCard[] }) {
  const open = (category: string) => vacancies.filter((v) => v.category === category).length

  return (
    <section aria-labelledby="categorias-titulo">
      <h2 id="categorias-titulo" className="mb-5 text-[22px] leading-7">
        Categorias
      </h2>
      <ul className="m-0 grid list-none grid-cols-2 gap-3 p-0 min-[480px]:grid-cols-3 md:grid-cols-4 xl:grid-cols-7">
        {CATEGORIES.map(({ value, label }) => {
          const count = open(value)
          return (
            <li key={value} className="min-w-0">
              <Link
                to={`/vagas?category=${value}`}
                className="group flex h-full flex-col items-center gap-3 rounded-[24px] bg-ficha px-3 py-5 text-center no-underline transition-colors hover:bg-controle motion-reduce:transition-none"
              >
                <span className="grid size-12 place-items-center rounded-full bg-papel">
                  <CategoryIcon category={value} className="size-6" strokeWidth={1.25} />
                </span>
                <span className="text-[13px] leading-4">{label}</span>
                {count > 0 && (
                  <span className="text-[12px] leading-4 text-tinta-media">
                    {count} {count === 1 ? 'vaga' : 'vagas'}
                  </span>
                )}
              </Link>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
