import {
  Briefcase,
  Building2,
  ClipboardCheck,
  ClipboardList,
  Search,
  Star,
  UserRound,
  Wallet,
  type LucideIcon,
} from 'lucide-react'
import { useEffect } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import type { Role } from '../api'
import { useAuth } from '../authContext'
import Logo from './Logo'
import NotificationBell from './NotificationBell'
import { Alert, Button } from './ui'

const MENU: Record<Role, { to: string; label: string; short: string; icon: LucideIcon }[]> = {
  COMPANY: [
    { to: '/empresa/vagas', label: 'Minhas vagas', short: 'Vagas', icon: ClipboardList },
    { to: '/empresa/confirmar-presenca', label: 'Confirmar presença', short: 'Presença', icon: ClipboardCheck },
    { to: '/empresa/avaliacoes', label: 'Avaliações', short: 'Avaliações', icon: Star },
    { to: '/empresa/perfil', label: 'Perfil da empresa', short: 'Perfil', icon: Building2 },
  ],
  WORKER: [
    { to: '/vagas', label: 'Buscar vagas', short: 'Buscar', icon: Search },
    { to: '/meus-trabalhos', label: 'Meus trabalhos', short: 'Trabalhos', icon: Briefcase },
    { to: '/carteira', label: 'Carteira', short: 'Carteira', icon: Wallet },
    { to: '/prestador/perfil', label: 'Meu perfil', short: 'Perfil', icon: UserRound },
  ],
  ADMIN: [],
}

/** Menu de quem ainda não entrou: os atalhos da página inicial. */
const PUBLIC_MENU = [
  { to: '/vagas', label: 'Vagas' },
  { to: '/#como-funciona', label: 'Como funciona' },
  { to: '/#perguntas', label: 'Perguntas' },
]

export default function Layout() {
  const { user, loading, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  // Nova tela começa do topo; um atalho com âncora (/#perguntas) rola até a seção.
  useEffect(() => {
    const target = location.hash ? document.getElementById(location.hash.slice(1)) : null
    if (target) target.scrollIntoView()
    else window.scrollTo(0, 0)
  }, [location.pathname, location.hash])

  // A página inicial pública usa a grade larga; as telas de trabalho ficam na coluna de leitura.
  const isLanding = !user && location.pathname === '/'

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  return (
    <>
      <a className="pular" href="#conteudo">
        Ir para o conteúdo
      </a>
      <header className="app-header">
        {user && (
          <Link to="/" className="app-brand app-brand-logado">
            <Logo />
          </Link>
        )}
        {user ? (
          <nav className="app-nav" aria-label="Menu principal">
            {MENU[user.role].map((item) => (
              <NavLink key={item.to} to={item.to} aria-label={item.label}>
                <item.icon className="app-nav-icone" aria-hidden="true" />
                <span className="rotulo-longo">{item.label}</span>
                <span className="rotulo-curto" aria-hidden="true">
                  {item.short}
                </span>
              </NavLink>
            ))}
            {user.role === 'ADMIN' && <a href="/admin/">Painel administrativo</a>}
          </nav>
        ) : (
          !loading && (
            <nav className="app-nav" aria-label="Menu principal">
              {PUBLIC_MENU.map((item) => (
                <Link key={item.to} to={item.to}>
                  {item.label}
                </Link>
              ))}
            </nav>
          )
        )}
        <div className="app-header-actions">
          {user ? (
            <>
              <NotificationBell />
              <Button variant="ghost" onClick={handleLogout}>
                Sair
              </Button>
            </>
          ) : (
            <Link to="/login" className="btn btn-ghost">
              Entrar
            </Link>
          )}
        </div>
      </header>
      {!user && (
        <Link to="/" className="app-brand">
          <Logo />
        </Link>
      )}
      <main className={isLanding ? 'app-main app-main-larga' : 'app-main'} id="conteudo">
        {user?.role === 'COMPANY' && user.verification_status === 'PENDENTE' && (
          <Alert tone="info">
            Cadastro em análise: você poderá publicar vagas após a aprovação
          </Alert>
        )}
        {/* A chave reinicia a entrada a cada troca de tela: mostra que a página mudou. */}
        <div className="tela" key={location.pathname}>
          <Outlet />
        </div>
      </main>
      <footer className="app-footer">
        <div className="grid grid-cols-1 gap-6 rounded-cartao bg-ficha p-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] md:gap-coluna md:p-8 xl:grid-cols-3">
          <h2 className="m-0 text-2xl leading-8">
            Turno combinado,
            <br />
            pagamento garantido.
          </h2>
          <p className="m-0 max-w-none text-[13px] leading-6 text-tinta-media">
            O Conecta Já liga empresas a prestadores autônomos para turnos curtos de trabalho
            manual. O valor fica retido antes de o turno começar e é liberado quando a presença é
            confirmada.
          </p>
          <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13px] leading-6 md:col-start-2 xl:col-auto xl:items-end">
            <li>Pagamento em custódia</li>
            <li>Cadastros verificados</li>
            <li>Presença por localização</li>
          </ul>
        </div>
        <div className="mt-6 flex flex-col justify-between gap-2 px-1 text-[13px] leading-6 text-tinta-media md:flex-row">
          <p className="m-0 max-w-none">© 2026 Conecta Já</p>
          <p className="m-0 max-w-none">
            Projeto acadêmico de Engenharia da Computação · Mackenzie
          </p>
        </div>
      </footer>
    </>
  )
}
