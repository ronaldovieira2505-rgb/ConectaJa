import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import VacancyCover from './VacancyCover'

/** Linha do histórico de um perfil: miniatura da vaga, título, contexto e o valor ao lado. */
export default function HistoryItem({
  to,
  title,
  subtitle,
  photoUrl,
  category,
  aside,
}: {
  to: string
  title: string
  subtitle: ReactNode
  photoUrl: string | null | undefined
  category: string
  aside?: ReactNode
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-regua py-4 last:border-b-0">
      <VacancyCover
        photoUrl={photoUrl}
        category={category}
        className="size-14 shrink-0 rounded-2xl"
      />
      <div className="flex min-w-[10rem] flex-1 flex-col gap-0.5">
        <Link to={to} className="text-[15px] leading-6">
          {title}
        </Link>
        <span className="text-[13px] leading-5 text-tinta-media">{subtitle}</span>
      </div>
      {aside && <div className="ml-auto flex shrink-0 flex-col items-end gap-1">{aside}</div>}
    </li>
  )
}
