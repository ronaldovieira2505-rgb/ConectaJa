import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type FavoriteCard } from '../api'
import JobsTabs from '../components/JobsTabs'
import { Alert, Card, Loading } from '../components/ui'
import VacancyTile from '../components/VacancyTile'

/** Aba "Favoritas" de "Meus trabalhos" (US18): vagas salvas, da que começa antes para a última. */
export default function FavoritesPage() {
  const [items, setItems] = useState<FavoriteCard[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api<{ results: FavoriteCard[] }>('/api/workers/me/favorites/')
      .then((data) => setItems(data.results))
      .catch((err: Error) => setError(err.message))
  }, [])

  function removed(id: number) {
    setItems((list) => list && list.filter((item) => item.id !== id))
  }

  return (
    <>
      <h1>Meus trabalhos</h1>
      <JobsTabs />
      <h2>Favoritas</h2>
      {error && <Alert tone="error">{error}</Alert>}
      {!items && !error && <Loading />}
      {items && items.length === 0 && (
        <Card>
          <div className="vazio">
            <h2>Nenhuma vaga salva</h2>
            <p>Toque no coração de uma vaga para guardá-la aqui.</p>
            <Link to="/vagas" className="btn btn-primary">
              Buscar vagas
            </Link>
          </div>
        </Card>
      )}
      {items && items.length > 0 && (
        <ul className="m-0 grid list-none grid-cols-1 gap-4 p-0 min-[600px]:grid-cols-2 min-[900px]:grid-cols-3">
          {items.map((item) => (
            <li key={item.id} className="min-w-0">
              <VacancyTile
                vacancy={item}
                tag={item.closed_label}
                linkable={item.closed_label !== 'Encerrada'}
                onFavoriteChange={(favorite) => !favorite && removed(item.id)}
              />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
