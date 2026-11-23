import { categoryGradient } from '../categoryColors'
import CategoryIcon from './CategoryIcon'

/** Pontilhado claro sobre o gradiente: dá textura à capa sem competir com o ícone. */
const DOTS = 'radial-gradient(rgb(255 255 255 / 22%) 1.2px, transparent 1.3px)'

/**
 * Imagem da vaga: a foto do local enviada pela empresa ou, sem foto, a capa da categoria.
 * `alt` vazio quando o título da vaga já está ao lado.
 */
export default function VacancyCover({
  photoUrl,
  category,
  alt = '',
  className = '',
}: {
  photoUrl: string | null | undefined
  category: string
  alt?: string
  className?: string
}) {
  if (photoUrl) {
    return (
      <img
        src={photoUrl}
        alt={alt}
        loading="lazy"
        className={`block bg-ficha object-cover ${className}`}
      />
    )
  }
  return (
    <span
      className={`relative grid place-items-center overflow-hidden ${className}`}
      style={{ backgroundImage: `${DOTS}, ${categoryGradient(category)}`, backgroundSize: '14px 14px, auto' }}
      aria-hidden="true"
    >
      <span className="absolute -right-[12%] -bottom-[30%] aspect-square w-[55%] rounded-full bg-white/12" />
      <CategoryIcon
        category={category}
        className="relative size-[34%] max-h-24 max-w-24 text-white drop-shadow-[0_6px_14px_rgb(0_0_0/18%)]"
        strokeWidth={1.1}
      />
    </span>
  )
}
