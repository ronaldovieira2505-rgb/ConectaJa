import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

type Handler = (init?: RequestInit) => { status?: number; body?: unknown }

function mockApi(handlers: Record<string, Handler>) {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${path}`
      const handler = handlers[key]
      if (!handler) throw new Error(`Chamada inesperada: ${key}`)
      const { status = 200, body } = handler(init)
      return Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) })
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

const anonymous: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({ status: 403, body: {} }),
}

const companySummary = {
  id: 3,
  name: 'Mercado Bom',
  logo_url: null,
  district: 'Centro',
  city: 'São Paulo',
  state: 'SP',
  member_since: '2026-08-10T12:00:00Z',
  rating: { average: 4.8, count: 20 },
  completed_shifts: 30,
  description: 'Supermercado de bairro.',
  profile_available: true,
  premium: true,
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
  company_rating: { average: 4.8, count: 20 },
  company_premium: true,
}

describe('Selo de contratante premium (US66)', () => {
  it('aparece na página da empresa com a explicação ao tocar', async () => {
    mockApi({
      ...anonymous,
      'GET /api/companies/3/public/': () => ({
        body: { ...companySummary, open_vacancies: [], recent_reviews: [] },
      }),
    })
    renderAt('/empresas/3')

    const badge = await screen.findByRole('button', { name: '★ Contratante premium' })
    expect(badge).toHaveAttribute('title', expect.stringContaining('boas avaliações'))
    await userEvent.click(badge)
    expect(screen.getByRole('note')).toHaveTextContent(/nenhuma contestação perdida/)
    await userEvent.click(badge)
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('aparece no detalhe da vaga ao lado do nome, uma vez', async () => {
    mockApi({
      ...anonymous,
      'GET /api/vacancies/7/': () => ({
        body: {
          ...card,
          description: 'Repor gôndolas.',
          street: 'Rua A',
          number: '1',
          latitude: -23.5,
          longitude: -46.6,
          can_apply: false,
          apply_blocker: null,
          my_application: null,
          company: companySummary,
        },
      }),
    })
    renderAt('/vagas/7')

    expect(await screen.findAllByRole('button', { name: '★ Contratante premium' })).toHaveLength(1)
  })

  it('a empresa sem selo vê o que falta no próprio perfil', async () => {
    mockApi({
      'GET /api/auth/me/': () => ({
        body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
      }),
      'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
      'GET /api/companies/me/': () => ({
        body: {
          id: 3,
          name: 'Acme',
          legal_name: 'Acme LTDA',
          trade_name: 'Acme',
          cnpj: '11222333000181',
          state_registration: '',
          tax_regime_label: 'Simples Nacional',
          registration_status: 'ATIVA',
          street: '',
          number: '',
          complement: '',
          district: '',
          city: '',
          state: '',
          zip_code: '',
          phone: '',
          payment_method_label: 'PIX',
          verification_status: 'APROVADA',
          verification_label: 'Aprovada',
          is_suspended: false,
          suspension_message: '',
          description: '',
          logo_url: null,
          member_since: '2026-08-10T12:00:00Z',
          stats: { published_vacancies: 4, completed_shifts: 7, total_paid_cents: 70000 },
          premium: {
            active: false,
            since: null,
            missing: ['3 turnos pagos', 'nota média de pelo menos 4,5 (hoje 4,2)'],
            explanation: 'Contratante premium: empresa com histórico...',
          },
        },
      }),
      'GET /api/vacancies/': () => ({ body: { total_retained_cents: 0, results: [] } }),
    })
    renderAt('/empresa/perfil')

    const list = await screen.findByRole('list', { name: 'O que falta para o selo' })
    expect(within(list).getByText('3 turnos pagos')).toBeInTheDocument()
    expect(within(list).getByText('nota média de pelo menos 4,5 (hoje 4,2)')).toBeInTheDocument()
  })
})
