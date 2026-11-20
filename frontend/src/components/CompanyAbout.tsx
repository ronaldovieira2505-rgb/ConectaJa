import { Link } from 'react-router-dom'
import { formatMonthYear, ratingLabel, type CompanySummary } from '../api'
import Avatar from './Avatar'

function placeOf(company: CompanySummary) {
  const city = [company.city, company.state].filter(Boolean).join('/')
  return [company.district, city].filter(Boolean).join(', ')
}

/**
 * "Sobre a empresa" (US15): logo, nome fantasia, bairro e cidade, tempo na plataforma, nota,
 * turnos realizados e a descrição. Sem descrição, o texto é omitido.
 */
export default function CompanyAbout({
  company,
  showProfileLink = false,
  heading: Heading = 'h2',
}: {
  company: CompanySummary
  showProfileLink?: boolean
  heading?: 'h1' | 'h2' | 'h3'
}) {
  const place = placeOf(company)
  const shifts = company.completed_shifts
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-4">
        <Avatar src={company.logo_url} name={company.name} kind="company" className="size-16" />
        <div className="flex min-w-[10rem] flex-1 flex-col gap-1">
          <Heading className="m-0 text-[17px] leading-6 tracking-normal">{company.name}</Heading>
          {place && <p className="m-0 text-[13px] leading-5 text-tinta-media">{place}</p>}
          <p className="m-0 text-[13px] leading-5 text-tinta-media">
            Na plataforma desde {formatMonthYear(company.member_since)}
          </p>
        </div>
      </div>
      <p className="m-0 text-[13px] leading-5">
        {ratingLabel(company.rating)} · {shifts} {shifts === 1 ? 'turno realizado' : 'turnos realizados'}
      </p>
      {company.description && <p className="descricao m-0">{company.description}</p>}
      {showProfileLink && company.profile_available && (
        <p className="m-0">
          <Link to={`/empresas/${company.id}`}>Ver perfil da empresa</Link>
        </p>
      )}
    </div>
  )
}
