import { useState, type FormEvent } from 'react'
import { api, ApiError, type PortfolioPhoto } from '../api'
import { Alert, Button, Card, Field } from './ui'

const MAX_PHOTOS = 8
const CAPTION_MAX = 120

/** "Trabalhos anteriores" (US09): até 8 fotos com legenda, privadas. */
export default function PortfolioCard({
  photos,
  onChange,
}: {
  photos: PortfolioPhoto[]
  onChange: (photos: PortfolioPhoto[]) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [caption, setCaption] = useState('')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [removingId, setRemovingId] = useState<number | null>(null)
  const full = photos.length >= MAX_PHOTOS

  async function add(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (!file) {
      setError('Escolha uma foto.')
      return
    }
    const form = new FormData()
    form.append('photo', file)
    form.append('caption', caption)
    setSending(true)
    try {
      const data = await api<{ results: PortfolioPhoto[] }>('/api/workers/me/portfolio/', {
        method: 'POST',
        form,
      })
      onChange(data.results)
      setFile(null)
      setCaption('')
      ;(event.target as HTMLFormElement).reset()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível enviar a foto.')
    } finally {
      setSending(false)
    }
  }

  async function remove(id: number) {
    setError('')
    try {
      await api(`/api/workers/me/portfolio/${id}/`, { method: 'DELETE' })
      onChange(photos.filter((photo) => photo.id !== id))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível remover a foto.')
    } finally {
      setRemovingId(null)
    }
  }

  return (
    <Card>
      <h2>Trabalhos anteriores</h2>
      <p className="sub">
        Mostre serviços que você já fez. As fotos só aparecem para as empresas em que você se
        candidatar.
      </p>
      {photos.length > 0 && (
        <ul className="m-0 grid list-none grid-cols-2 gap-3 p-0 min-[520px]:grid-cols-4">
          {photos.map((photo) => (
            <li key={photo.id} className="flex flex-col gap-2">
              <img
                src={photo.url}
                alt={photo.caption || 'Trabalho anterior'}
                className="aspect-square w-full rounded-2xl bg-ficha object-cover"
              />
              {photo.caption && <span className="text-[13px] leading-5">{photo.caption}</span>}
              {removingId === photo.id ? (
                <span className="flex flex-wrap gap-2">
                  <Button variant="secondary" onClick={() => remove(photo.id)}>
                    Confirmar remoção
                  </Button>
                  <Button variant="ghost" onClick={() => setRemovingId(null)}>
                    Voltar
                  </Button>
                </span>
              ) : (
                <Button
                  variant="secondary"
                  aria-label={`Remover ${photo.caption || 'foto'}`}
                  onClick={() => setRemovingId(photo.id)}
                >
                  Remover
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {full ? (
        <p className="sub">Você já tem {MAX_PHOTOS} fotos. Remova uma para adicionar outra.</p>
      ) : (
        <form onSubmit={add} noValidate>
          <Field
            label="Adicionar foto"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Field
            label="Legenda (opcional)"
            maxLength={CAPTION_MAX}
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
          />
          <p className="sub">JPG, PNG ou WebP, até 5 MB.</p>
          <div className="acoes">
            <Button type="submit" variant="secondary" busy={sending}>
              Enviar foto
            </Button>
          </div>
        </form>
      )}
      {error && <Alert tone="error">{error}</Alert>}
    </Card>
  )
}
