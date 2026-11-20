import { Heart } from 'lucide-react'
import { useState, type MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../authContext'

/**
 * Coração de favoritos (US18). Prestador salva ou remove; visitante vai para o login e volta
 * para a vaga; empresa e admin não veem o botão.
 */
export default function FavoriteButton({
  vacancyId,
  title,
  initial = false,
  onChange,
  className = '',
}: {
  vacancyId: number
  title: string
  initial?: boolean
  onChange?: (favorite: boolean) => void
  className?: string
}) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [favorite, setFavorite] = useState(initial)
  const [busy, setBusy] = useState(false)

  if (user && user.role !== 'WORKER') return null

  async function toggle(event: MouseEvent) {
    event.preventDefault()
    event.stopPropagation()
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(`/vagas/${vacancyId}`)}`)
      return
    }
    const next = !favorite
    setFavorite(next)
    setBusy(true)
    try {
      await api(`/api/vacancies/${vacancyId}/favorite/`, { method: next ? 'POST' : 'DELETE' })
      onChange?.(next)
    } catch {
      setFavorite(!next) // não salvou: volta ao estado anterior
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-pressed={favorite}
      aria-label={favorite ? `Remover “${title}” dos favoritos` : `Salvar “${title}” nos favoritos`}
      className={`grid size-10 cursor-pointer place-items-center rounded-full border-0 bg-vidro text-tinta backdrop-blur-flutuante disabled:cursor-wait ${className}`}
    >
      <Heart
        className={`size-5 ${favorite ? 'fill-[var(--oxido)] text-[var(--oxido)]' : ''}`}
        strokeWidth={1.5}
        aria-hidden="true"
      />
    </button>
  )
}
