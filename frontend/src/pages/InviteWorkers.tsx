import { useCallback, useState } from 'react'
import { api, ApiError, type PastWorkersList } from '../api'
import Avatar from '../components/Avatar'
import { Alert, Badge, Button } from '../components/ui'

function ratingText(rating: number | null) {
  if (rating === null) return 'Você ainda não avaliou'
  return `Nota que você deu: ★ ${rating.toLocaleString('pt-BR', { minimumFractionDigits: 1 })}`
}

/**
 * "Convidar prestadores" (US44): quem já concluiu turno pago com a empresa. O convite só avisa;
 * o prestador se candidata normalmente e a empresa aprova como sempre.
 */
export default function InviteWorkersSection({ vacancyId }: { vacancyId: number }) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<PastWorkersList | null>(null)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await api<PastWorkersList>(`/api/company/past-workers/?vacancy=${vacancyId}`))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível carregar os prestadores.')
    }
  }, [vacancyId])

  async function toggle() {
    const next = !open
    setOpen(next)
    if (next && !data) await load()
  }

  async function invite(workerId: number) {
    setError('')
    setBusyId(workerId)
    try {
      await api(`/api/vacancies/${vacancyId}/invite/`, {
        method: 'POST',
        body: { worker_id: workerId },
      })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível enviar o convite.')
    } finally {
      setBusyId(null)
    }
    await load()
  }

  return (
    <section aria-labelledby="convidar-titulo">
      <h2 id="convidar-titulo">Convidar prestadores</h2>
      <p className="sub">
        Avise quem já trabalhou bem com você. O prestador se candidata e você aprova como sempre.
      </p>
      <div className="acoes">
        <Button variant="secondary" aria-expanded={open} onClick={toggle}>
          {open ? 'Ocultar lista' : 'Convidar prestadores'}
        </Button>
      </div>
      {open && error && <Alert tone="error">{error}</Alert>}
      {open && data && (
        <>
          {data.vacancy_blocker && <Alert tone="info">{data.vacancy_blocker}</Alert>}
          {!data.vacancy_blocker && (
            <p className="sub">
              Restam {data.invites_left} de {data.max_invites} convites para esta vaga.
            </p>
          )}
          {data.results.length === 0 ? (
            <p>Ninguém concluiu um turno pago com a sua empresa ainda.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {data.results.map((w) => (
                <li key={w.worker_id} className="flex flex-wrap items-center gap-3 rounded-cartao bg-white p-4">
                  <Avatar src={w.photo_url} name={w.name} className="size-12" />
                  <div className="flex min-w-[10rem] flex-1 flex-col">
                    <strong>{w.name}</strong>
                    <span className="text-[13px] leading-5 text-tinta-media">
                      {w.shifts_with_company}{' '}
                      {w.shifts_with_company === 1 ? 'turno com você' : 'turnos com você'} ·{' '}
                      {ratingText(w.rating_given)}
                    </span>
                  </div>
                  {w.invited ? (
                    <Badge tone="success">Convidado</Badge>
                  ) : w.blocker ? (
                    <span className="text-[13px] leading-5 text-tinta-media">{w.blocker}</span>
                  ) : (
                    <Button
                      busy={busyId === w.worker_id}
                      disabled={Boolean(data.vacancy_blocker) || data.invites_left === 0}
                      aria-label={`Convidar ${w.name}`}
                      onClick={() => invite(w.worker_id)}
                    >
                      Convidar
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
