import { NavLink } from 'react-router-dom'

const tab = ({ isActive }: { isActive: boolean }) =>
  `btn ${isActive ? 'btn-primary' : 'btn-secondary'}`

/** Abas de "Meus trabalhos": os trabalhos e as vagas favoritas (US18). */
export default function JobsTabs() {
  return (
    <nav aria-label="Abas de Meus trabalhos" className="acoes">
      <NavLink end to="/meus-trabalhos" className={tab}>
        Trabalhos
      </NavLink>
      <NavLink to="/meus-trabalhos/favoritas" className={tab}>
        Favoritas
      </NavLink>
    </nav>
  )
}
