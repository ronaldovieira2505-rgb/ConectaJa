import { useEffect, useState } from 'react'
import { api, ratingLabel, type CompanyReviews } from '../api'
import { Alert, Card, Loading } from '../components/ui'

/** Avaliações que a empresa recebeu dos prestadores (US64). O prestador aparece como "Ana S.". */
export default function CompanyReviewsPage() {
  const [data, setData] = useState<CompanyReviews | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api<CompanyReviews>('/api/company/reviews/')
      .then(setData)
      .catch((err: Error) => setError(err.message))
  }, [])

  if (error) return <Alert tone="error">{error}</Alert>
  if (!data) return <Loading />

  return (
    <>
      <h1>Avaliações recebidas</h1>
      <p className="sub">{ratingLabel(data.summary)}</p>
      {data.results.length === 0 ? (
        <Card>
          <div className="vazio">
            <h2>Sem avaliações ainda</h2>
            <p>Os prestadores podem avaliar sua empresa depois que as horas forem aprovadas.</p>
          </div>
        </Card>
      ) : (
        <Card>
          <ul className="m-0 list-none p-0">
            {data.results.map((review) => (
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
                  {review.reviewer} · {review.vacancy_title}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  )
}
