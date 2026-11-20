import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type CompanyPublicProfile } from '../api'
import CompanyAbout from '../components/CompanyAbout'
import { Alert, Card, Loading } from '../components/ui'
import VacancyTile from '../components/VacancyTile'

function formatDay(iso: string) {
  return new Date(iso).toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo' })
}

/** Página pública da empresa (US15): dados públicos, vagas abertas e avaliações recentes. */
export default function CompanyPublicPage() {
  const { id } = useParams()
  const [company, setCompany] = useState<CompanyPublicProfile | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api<CompanyPublicProfile>(`/api/companies/${id}/public/`)
      .then(setCompany)
      .catch((err: Error) => setError(err.message))
  }, [id])

  if (error) return <Alert tone="error">{error}</Alert>
  if (!company) return <Loading rows={2} />

  return (
    <>
      <Card tone="carimbo">
        <p>
          <Link to="/vagas">Voltar para a busca</Link>
        </p>
        <CompanyAbout company={company} heading="h1" />
      </Card>

      <section aria-labelledby="empresa-vagas">
        <h2 id="empresa-vagas">Vagas abertas</h2>
        {company.open_vacancies.length === 0 ? (
          <p>Nenhuma vaga aberta no momento.</p>
        ) : (
          <ul className="m-0 grid list-none grid-cols-1 gap-4 p-0 min-[600px]:grid-cols-2 min-[900px]:grid-cols-3">
            {company.open_vacancies.map((vacancy) => (
              <li key={vacancy.id} className="min-w-0">
                <VacancyTile vacancy={vacancy} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="empresa-avaliacoes">
        <h2 id="empresa-avaliacoes">Avaliações recentes</h2>
        {company.recent_reviews.length === 0 ? (
          <p>Sem avaliações ainda.</p>
        ) : (
          <Card>
            <ul className="m-0 list-none p-0">
              {company.recent_reviews.map((review) => (
                <li
                  key={review.id}
                  className="flex flex-col gap-1 border-b border-regua py-4 last:border-b-0"
                >
                  <span role="img" aria-label={`Nota ${review.rating} de 5`}>
                    {'★'.repeat(review.rating)}
                    {'☆'.repeat(5 - review.rating)}
                  </span>
                  {review.comment && <p className="m-0">{review.comment}</p>}
                  <span className="text-[13px] leading-5 text-tinta-media">
                    {review.reviewer} · {formatDay(review.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </section>
    </>
  )
}
