import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, brl, formatShift, type Vacancy, type VacancyList } from '../api'
import { Alert, Badge, Card, Loading, Slots } from '../components/ui'
import VacancyCover from '../components/VacancyCover'
import { badgeToneFor } from '../status'

/** Uma vaga por cartão: imagem do local, estado, valor por pessoa e posições. */
function VacancyRow({ vacancy }: { vacancy: Vacancy }) {
  return (
    <li className="min-w-0">
      <article className="relative flex h-full flex-col overflow-hidden rounded-[24px] border border-regua bg-papel transition-shadow focus-within:shadow-[0_8px_24px_rgb(32_32_32/8%)] hover:shadow-[0_8px_24px_rgb(32_32_32/8%)] motion-reduce:transition-none">
        <VacancyCover
          photoUrl={vacancy.photo_url}
          category={vacancy.category}
          className="aspect-[16/9] w-full"
        />
        <div className="flex flex-1 flex-col gap-3 p-5">
          <p className="m-0">
            <Badge tone={badgeToneFor(vacancy.status)}>{vacancy.status_label}</Badge>
          </p>
          <div className="flex flex-col gap-1">
            <h2 className="m-0 text-[17px] leading-6 tracking-normal text-balance">
              <Link to={`/empresa/vagas/${vacancy.id}`} className="no-underline after:absolute after:inset-0 after:rounded-[24px] after:content-[''] focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:-outline-offset-2 focus-visible:after:outline-foco">
                {vacancy.title}
              </Link>
            </h2>
            <p className="m-0 text-[13px] leading-5 text-tinta-media">
              {formatShift(vacancy.starts_at, vacancy.ends_at)}
            </p>
            {/* Acima do link que cobre o cartão, para continuar clicável (US25). */}
            <Link
              to={`/empresa/vagas/nova?duplicar=${vacancy.id}`}
              className="relative z-10 self-start text-[13px] leading-5"
              aria-label={`Duplicar ${vacancy.title}`}
            >
              Duplicar
            </Link>
          </div>
          <div className="mt-auto flex items-end justify-between gap-3 border-t border-regua pt-4">
            <p className="m-0 flex flex-col">
              <span className="text-[12px] leading-4 text-tinta-media">Por pessoa</span>
              <span className="text-[22px] leading-7">{brl(vacancy.pay_per_person_cents)}</span>
            </p>
            <Slots filled={vacancy.filled_positions} total={vacancy.positions} />
          </div>
        </div>
      </article>
    </li>
  )
}

/** Minhas vagas: total retido em custódia e uma ficha por vaga. */
export default function CompanyVacanciesPage() {
  const [data, setData] = useState<VacancyList | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api<VacancyList>('/api/company/vacancies/')
      .then(setData)
      .catch(() => setError('Não foi possível carregar as suas vagas.'))
  }, [])

  if (!data && !error) return <Loading />

  return (
    <>
      <Card tone="carimbo">
        <h1>Minhas vagas</h1>
        <p>
          Total retido em custódia
          <strong className="dinheiro">{brl(data?.total_retained_cents ?? 0)}</strong>
        </p>
        <div className="acoes">
          <Link to="/empresa/vagas/nova" className="btn btn-primary">
            Nova vaga
          </Link>
        </div>
      </Card>

      {error && <Alert tone="error">{error}</Alert>}

      {data &&
        (data.results.length === 0 ? (
          <Card>
            <div className="vazio">
              <h2>Publique o primeiro turno</h2>
              <p>A vaga aparece na busca assim que o pagamento é confirmado.</p>
              <Link to="/empresa/vagas/nova" className="btn btn-primary">
                Nova vaga
              </Link>
            </div>
          </Card>
        ) : (
          <ul className="m-0 mt-6 grid list-none grid-cols-1 gap-4 p-0 min-[600px]:grid-cols-2 min-[900px]:grid-cols-3">
            {data.results.map((v) => (
              <VacancyRow key={v.id} vacancy={v} />
            ))}
          </ul>
        ))}
    </>
  )
}
