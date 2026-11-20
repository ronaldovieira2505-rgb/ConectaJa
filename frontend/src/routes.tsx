import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import type { Role } from './api'
import { homePathFor, useAuth } from './authContext'
import Layout from './components/Layout'
import { Loading } from './components/ui'
import CompanyConfirmPresencePage from './pages/CompanyConfirmPresencePage'
import CompanyProfilePage from './pages/CompanyProfilePage'
import CompanyPublicPage from './pages/CompanyPublicPage'
import CompanyReviewsPage from './pages/CompanyReviewsPage'
import CompanySignupPage from './pages/CompanySignupPage'
import CompanyVacanciesPage from './pages/CompanyVacanciesPage'
import CompanyVacancyDetailPage from './pages/CompanyVacancyDetailPage'
import CompanyVacancyNewPage from './pages/CompanyVacancyNewPage'
import FavoritesPage from './pages/FavoritesPage'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import MyJobsPage from './pages/MyJobsPage'
import WorkerWalletPage from './pages/WorkerWalletPage'
import VacancyPublicDetailPage from './pages/VacancyPublicDetailPage'
import VacancySearchPage from './pages/VacancySearchPage'
import SignupChoicePage from './pages/SignupChoicePage'
import WorkerDocumentsPage from './pages/WorkerDocumentsPage'
import WorkerHomePage from './pages/WorkerHomePage'
import WorkerPixPage from './pages/WorkerPixPage'
import WorkerSignupPage from './pages/WorkerSignupPage'

/** Manda para o login quem não está autenticado e para a home do papel quem não tem acesso. */
function RequireRole({ role }: { role: Role }) {
  const { user, loading } = useAuth()
  if (loading) return <Loading rows={1} />
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== role) return <Navigate to={homePathFor(user.role)} replace />
  return <Outlet />
}

function Home() {
  const { user, loading } = useAuth()
  const location = useLocation()
  const accountDeleted = Boolean(
    (location.state as { accountDeleted?: boolean } | null)?.accountDeleted,
  )
  if (loading) return <Loading rows={1} />
  // Visitante vê a página inicial; quem já entrou vai direto para a área do seu papel.
  // Conta recém-excluída (US11): fica na página inicial, que encerra a sessão local.
  return user && !accountDeleted ? <Navigate to={homePathFor(user.role)} replace /> : <LandingPage />
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="cadastro" element={<SignupChoicePage />} />
        <Route path="cadastro/empresa" element={<CompanySignupPage />} />
        <Route path="cadastro/prestador" element={<WorkerSignupPage />} />
        {/* Busca pública: quem não pode se candidatar vê o que falta (US12). */}
        <Route path="vagas" element={<VacancySearchPage />} />
        <Route path="vagas/:id" element={<VacancyPublicDetailPage />} />
        {/* Perfil público da empresa, aberto a qualquer pessoa (US15). */}
        <Route path="empresas/:id" element={<CompanyPublicPage />} />
        <Route element={<RequireRole role="COMPANY" />}>
          <Route path="empresa/vagas" element={<CompanyVacanciesPage />} />
          <Route path="empresa/vagas/nova" element={<CompanyVacancyNewPage />} />
          <Route path="empresa/vagas/:id" element={<CompanyVacancyDetailPage />} />
          <Route path="empresa/confirmar-presenca" element={<CompanyConfirmPresencePage />} />
          <Route path="empresa/perfil" element={<CompanyProfilePage />} />
          <Route path="empresa/avaliacoes" element={<CompanyReviewsPage />} />
        </Route>
        <Route element={<RequireRole role="WORKER" />}>
          <Route path="prestador/vagas" element={<Navigate to="/vagas" replace />} />
          <Route path="meus-trabalhos" element={<MyJobsPage />} />
          <Route path="meus-trabalhos/favoritas" element={<FavoritesPage />} />
          <Route path="carteira" element={<WorkerWalletPage />} />
          <Route path="prestador/perfil" element={<WorkerHomePage />} />
          <Route path="perfil/documentos" element={<WorkerDocumentsPage />} />
          <Route path="perfil/pix" element={<WorkerPixPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
