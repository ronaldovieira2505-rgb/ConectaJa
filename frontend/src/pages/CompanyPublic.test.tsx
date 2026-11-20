import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

const company = {
  id: 3,
  name: 'Mercado Bom',
  logo_url: null,
  district: 'Centro',
  city: 'São Paulo',
  state: 'SP',
  member_since: '2026-08-10T12:00:00Z',
  rating: { average: 4.6, count: 12 },
  completed_shifts: 30,
  description: 'Supermercado de bairro com entregas.',
  profile_available: true,
}

const card = {
  id: 7,
  title: 'Reposição de estoque',
  company_name: 'Mercado Bom',
  category: 'VAREJO',
  category_label: 'Varejo',
  starts_at: '2026-11-25T12:00:00Z',
  ends_at: '2026-11-25T16:00:00Z',
  district: 'Centro',
  city: 'São Paulo',
  state: 'SP',
  gross_cents: 10000,
  fee_percent: 3,
  fee_cents: 300,
  net_cents: 9700,
  remaining_positions: 1,
  payment_guaranteed: true,
  urgent: false,
  distance_km: null,
  photo_url: null,
  company_rating: { average: 4.6, count: 12 },
}

/** Visitante sem login: `/api/auth/me/` responde 403 e o resto vem de `bodies`. */
function mockAnonymous(bodies: Record<string, { status?: number; body: unknown }>) {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string) => {
      if (path === '/api/auth/me/') {
        return Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({}) })
      }
      const found = bodies[path]
      if (!found) throw new Error(`Chamada inesperada: ${path}`)
      const status = found.status ?? 200
      return Promise.resolve({
        ok: status === 200,
        status,
        json: () => Promise.resolve(found.body),
      })
    }),
  )
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('Página pública da empresa (US15)', () => {
  it('mostra os dados públicos, as vagas abertas e as avaliações recentes', async () => {
    mockAnonymous({
      '/api/companies/3/public/': {
        body: {
          ...company,
          open_vacancies: [card],
          recent_reviews: [
            {
              id: 1,
              rating: 5,
              comment: 'Empresa organizada, pagou certinho.',
              created_at: '2026-11-10T12:00:00Z',
              reviewer: 'Ana R.',
            },
          ],
        },
      },
    })

    renderAt('/empresas/3')

    const title = await screen.findByRole('heading', { level: 1, name: 'Mercado Bom' })
    const header = within(title.closest('section') as HTMLElement)
    expect(header.getByText('Centro, São Paulo/SP')).toBeInTheDocument()
    expect(header.getByText(/Na plataforma desde/)).toBeInTheDocument()
    expect(header.getByText('★ 4,6 · 12 avaliações · 30 turnos realizados')).toBeInTheDocument()
    expect(header.getByText('Supermercado de bairro com entregas.')).toBeInTheDocument()
    const open = screen.getByRole('region', { name: 'Vagas abertas' })
    expect(within(open).getByRole('link', { name: 'Reposição de estoque' })).toBeInTheDocument()
    const reviews = screen.getByRole('region', { name: 'Avaliações recentes' })
    expect(within(reviews).getByText('Empresa organizada, pagou certinho.')).toBeInTheDocument()
    expect(within(reviews).getByText(/Ana R\./)).toBeInTheDocument()
    expect(screen.queryByText(/CNPJ/)).not.toBeInTheDocument()
  })

  it('mostra o aviso quando a empresa não tem página pública', async () => {
    mockAnonymous({
      '/api/companies/3/public/': { status: 404, body: { detail: 'Empresa não encontrada.' } },
    })

    renderAt('/empresas/3')

    expect(await screen.findByText('Empresa não encontrada.')).toBeInTheDocument()
  })
})

const detail = {
  ...card,
  description: 'Repor prateleiras.',
  street: 'Rua A',
  number: '1',
  complement: '',
  zip_code: '',
  latitude: '-23.550520',
  longitude: '-46.633308',
  can_apply: false,
  apply_blocker: 'Entre como prestador para se candidatar.',
  my_application: null,
  rules: {
    free_cancel_minutes_before: 1440,
    late_cancel_block_days: 7,
    geofence_radius_m: 150,
    checkin_open_minutes_before: 30,
    no_show_tolerance_minutes: 30,
    no_show_limit: 2,
    no_show_window_days: 30,
    suspension_days: 15,
    contest_window_minutes: 1440,
  },
}

describe('Sobre a empresa no detalhe da vaga (US15)', () => {
  it('mostra o bloco com o link para o perfil público', async () => {
    mockAnonymous({ '/api/vacancies/7/': { body: { ...detail, company } } })

    renderAt('/vagas/7')

    const about = await screen.findByRole('region', { name: 'Sobre a empresa' })
    expect(within(about).getByText('Supermercado de bairro com entregas.')).toBeInTheDocument()
    expect(within(about).getByText(/30 turnos realizados/)).toBeInTheDocument()
    expect(within(about).getByRole('link', { name: 'Ver perfil da empresa' })).toHaveAttribute(
      'href',
      '/empresas/3',
    )
  })

  it('omite a descrição vazia e o link de empresa sem perfil público', async () => {
    mockAnonymous({
      '/api/vacancies/7/': {
        body: { ...detail, company: { ...company, description: '', profile_available: false } },
      },
    })

    renderAt('/vagas/7')

    const about = await screen.findByRole('region', { name: 'Sobre a empresa' })
    expect(within(about).queryByText('Supermercado de bairro com entregas.')).not.toBeInTheDocument()
    expect(within(about).queryByRole('link', { name: 'Ver perfil da empresa' })).not.toBeInTheDocument()
    expect(within(about).getByRole('heading', { name: 'Mercado Bom' })).toBeInTheDocument()
  })
})
