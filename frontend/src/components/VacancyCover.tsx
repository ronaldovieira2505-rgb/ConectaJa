import { CATEGORIES } from '../categories'
import CategoryIcon from './CategoryIcon'

/** Tons do gradiente da marca: cada categoria fica com um, para a grade não ficar toda igual. */
const TINTS = [
  'bg-[color-mix(in_oklab,var(--gradiente-inicio)_18%,white)]',
  'bg-[color-mix(in_oklab,var(--gradiente-meio)_16%,white)]',
  'bg-[color-mix(in_oklab,var(--gradiente-fim)_18%,white)]',
]

function tintFor(category: string) {
  const index = CATEGORIES.findIndex((c) => c.value === category)
  return TINTS[(index < 0 ? 0 : index) % TINTS.length]
}

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
      className={`grid place-items-center ${tintFor(category)} ${className}`}
      aria-hidden="true"
    >
      <CategoryIcon
        category={category}
        className="size-[28%] max-h-20 max-w-20 text-tinta/60"
        strokeWidth={0.9}
      />
    </span>
  )
}
