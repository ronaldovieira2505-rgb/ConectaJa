import { useEffect, useState } from 'react'
import type { PortfolioPhoto } from '../api'
import { Button } from './ui'

const VISIBLE = 4

/**
 * Fotos de trabalhos anteriores do candidato (US41): até 4 miniaturas e "+N"; o clique abre a foto
 * em tamanho maior com a legenda e dá para passar para as outras. Sem fotos, nada aparece.
 */
export default function PortfolioThumbs({ photos, name }: { photos: PortfolioPhoto[]; name: string }) {
  const [index, setIndex] = useState<number | null>(null)

  useEffect(() => {
    if (index === null) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setIndex(null)
      if (event.key === 'ArrowRight') setIndex((i) => (i === null ? i : (i + 1) % photos.length))
      if (event.key === 'ArrowLeft')
        setIndex((i) => (i === null ? i : (i - 1 + photos.length) % photos.length))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [index, photos.length])

  if (photos.length === 0) return null
  const extra = photos.length - VISIBLE
  const current = index === null ? null : photos[index]

  return (
    <div>
      <ul className="m-0 flex list-none flex-wrap gap-2 p-0" aria-label={`Trabalhos anteriores de ${name}`}>
        {photos.slice(0, VISIBLE).map((photo, i) => (
          <li key={photo.id}>
            <button
              type="button"
              onClick={() => setIndex(i)}
              className="block cursor-pointer overflow-hidden rounded-xl border-0 p-0"
              aria-label={`Ver foto ${i + 1} de ${photos.length}${photo.caption ? `: ${photo.caption}` : ''}`}
            >
              <img src={photo.url} alt="" className="size-16 bg-ficha object-cover" />
            </button>
          </li>
        ))}
        {extra > 0 && (
          <li>
            <button
              type="button"
              onClick={() => setIndex(VISIBLE)}
              className="grid size-16 cursor-pointer place-items-center rounded-xl border-0 bg-controle text-[15px]"
              aria-label={`Ver mais ${extra} ${extra === 1 ? 'foto' : 'fotos'}`}
            >
              +{extra}
            </button>
          </li>
        )}
      </ul>
      {current && index !== null && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Trabalhos anteriores de ${name}`}
          className="fixed inset-0 z-50 grid place-items-center bg-[rgb(0_0_0/70%)] p-4"
          onClick={() => setIndex(null)}
        >
          <figure
            className="m-0 flex max-w-[720px] flex-col gap-3 rounded-cartao bg-papel p-4"
            onClick={(event) => event.stopPropagation()}
          >
            <img
              src={current.url}
              alt={current.caption || `Trabalho anterior de ${name}`}
              className="max-h-[70vh] w-full rounded-2xl object-contain"
            />
            <figcaption className="text-[15px] leading-6">
              {current.caption || 'Sem legenda'}{' '}
              <span className="text-tinta-media">
                · {index + 1} de {photos.length}
              </span>
            </figcaption>
            <div className="acoes">
              {photos.length > 1 && (
                <>
                  <Button
                    variant="secondary"
                    onClick={() => setIndex((index - 1 + photos.length) % photos.length)}
                  >
                    Anterior
                  </Button>
                  <Button variant="secondary" onClick={() => setIndex((index + 1) % photos.length)}>
                    Próxima
                  </Button>
                </>
              )}
              <Button onClick={() => setIndex(null)}>Fechar</Button>
            </div>
          </figure>
        </div>
      )}
    </div>
  )
}
