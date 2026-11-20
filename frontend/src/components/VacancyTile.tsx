import { CalendarClock, MapPin } from 'lucide-react'
import { Link } from 'react-router-dom'
import { brl, formatShift, ratingLabel, type VacancyCard } from '../api'
import FavoriteButton from './FavoriteButton'
import VacancyCover from './VacancyCover'

const META = 'flex items-center gap-2 text-[13px] leading-5 text-tinta-media'
const META_ICON = 'size-4 shrink-0'
const TAG = 'inline-flex min-h-7 items-center rounded-full px-3 text-[12px] leading-4 backdrop-blur-flutuante'

function place(vacancy: VacancyCard) {
  const city = vacancy.city && vacancy.state ? `${vacancy.city}/${vacancy.state}` : vacancy.city
  return [vacancy.district, city].filter(Boolean).join(', ')
}

/** Cartão de vaga da vitrine e da busca: imagem, o essencial do turno e o valor líquido. */
export default function VacancyTile({
  vacancy,
  heading: Heading = 'h3',
  tag,
  linkable = true,
  onFavoriteChange,
}: {
  vacancy: VacancyCard
  /** Nível do título, conforme a seção em que o cartão aparece. */
  heading?: 'h2' | 'h3'
  /** Selo extra sobre a imagem, como "Encerrada" ou "Lotada" nas favoritas (US18). */
  tag?: string | null
  /** Vaga encerrada não tem mais página pública: o cartão não vira link. */
  linkable?: boolean
  onFavoriteChange?: (favorite: boolean) => void
}) {
  return (
    <article className="relative flex h-full flex-col overflow-hidden rounded-[24px] border border-regua bg-papel transition-shadow focus-within:shadow-[0_8px_24px_rgb(32_32_32/8%)] hover:shadow-[0_8px_24px_rgb(32_32_32/8%)] motion-reduce:transition-none">
      <div className="relative">
        <VacancyCover
          photoUrl={vacancy.photo_url}
          category={vacancy.category}
          className="aspect-[16/9] w-full"
        />
        <p className="absolute top-3 right-3 left-3 m-0 flex max-w-none flex-wrap gap-1.5">
          <span className={`${TAG} bg-vidro`}>{vacancy.category_label}</span>
          {vacancy.urgent && <span className={`${TAG} bg-[var(--colete-fundo)]`}>Urgente</span>}
          {tag && <span className={`${TAG} bg-[var(--oxido-fundo)]`}>{tag}</span>}
        </p>
        {/* Acima do link que cobre o cartão, para o clique salvar em vez de abrir a vaga. */}
        <FavoriteButton
          vacancyId={vacancy.id}
          title={vacancy.title}
          initial={vacancy.favorite ?? false}
          onChange={onFavoriteChange}
          className="absolute right-3 bottom-3 z-10"
        />
      </div>
      <div className="flex flex-1 flex-col gap-3 p-5">
        <div className="flex flex-col gap-1">
          <Heading className="m-0 text-[17px] leading-6 tracking-normal text-balance">
            {linkable ? (
              <Link
                to={`/vagas/${vacancy.id}`}
                className="no-underline after:absolute after:inset-0 after:rounded-[24px] after:content-[''] focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:-outline-offset-2 focus-visible:after:outline-foco"
              >
                {vacancy.title}
              </Link>
            ) : (
              vacancy.title
            )}
          </Heading>
          <p className="m-0 text-[13px] leading-5 text-tinta-media">{vacancy.company_name}</p>
          <p className="m-0 text-[12px] leading-4 text-tinta-media">
            {ratingLabel(vacancy.company_rating)}
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <p className={`m-0 ${META}`}>
            <CalendarClock className={META_ICON} strokeWidth={1.25} aria-hidden="true" />
            {formatShift(vacancy.starts_at, vacancy.ends_at)}
          </p>
          <p className={`m-0 ${META}`}>
            <MapPin className={META_ICON} strokeWidth={1.25} aria-hidden="true" />
            {place(vacancy)}
            {vacancy.distance_km !== null && ` · ${vacancy.distance_km.toLocaleString('pt-BR')} km`}
          </p>
        </div>
        <div className="mt-auto flex items-end justify-between gap-3 border-t border-regua pt-4">
          <p className="m-0 flex flex-col">
            <span className="text-[12px] leading-4 text-tinta-media">Você recebe</span>
            <span className="text-[22px] leading-7">{brl(vacancy.net_cents)}</span>
          </p>
          <p className="m-0 text-[12px] leading-4 text-tinta-media">
            {vacancy.remaining_positions}{' '}
            {vacancy.remaining_positions === 1 ? 'vaga restante' : 'vagas restantes'}
          </p>
        </div>
      </div>
    </article>
  )
}
