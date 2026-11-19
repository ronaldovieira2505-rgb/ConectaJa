import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

const profile = {
  id: 3,
  name: 'Mercado Bom',
  legal_name: 'Mercado Bom LTDA',
  trade_name: 'Mercado Bom',
  cnpj: '11222333000181',
  state_registration: '',
  tax_regime_label: 'Simples Nacional',
  registration_status: 'ATIVA',
  street: 'Praça da Sé',
  number: '1',
  complement: '',
  district: 'Sé',
  city: 'São Paulo',
  state: 'SP',
  zip_code: '01001000',
  phone: '',
  payment_method_label: 'PIX',
  verification_status: 'APROVADA',
  verification_label: 'Aprovada',
  description: '',
  logo_url: null,
  member_since: '2026-10-02T12:00:00Z',
  stats: {
    published_vacancies: 4,
    finished_vacancies: 1,
    completed_shifts: 2,
    total_paid_cents: 20000,
  },
}

const finished = {
  id: 9,
  title: 'Inventário de fim de mês',
  category: 'VAREJO',
  category_label: 'Varejo',
  description: '',
  street: '',
  city: 'São Paulo',
  state: 'SP',
  latitude: '0',
  longitude: '0',
  starts_at: '2026-10-10T12:00:00Z',
  ends_at: '2026-10-10T16:00:00Z',
  pay_per_person_cents: 10000,
  positions: 2,
  filled_positions: 2,
  total_cents: 20000,
  retained_cents: 0,
  status: 'FINALIZADA',
  status_label: 'Finalizada',
  photo_url: null,
}

type Reply = { status?: number; body?: unknown }

function mockApi(extra: Record<string, (init?: RequestInit) => Reply> = {}) {
  const handlers: Record<string, (init?: RequestInit) => Reply> = {
    'GET /api/auth/me/': () => ({
      body: { id: 1, name: 'Ana', email: 'ana@example.com', role: 'COMPANY' },
    }),
    'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
    'GET /api/companies/me/': () => ({ body: profile }),
    'GET /api/company/vacancies/': () => ({
      body: { total_retained_cents: 0, results: [finished, { ...finished, id: 10, status: 'PUBLICADA' }] },
    }),
    ...extra,
  }
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      const handler = handlers[`${init?.method ?? 'GET'} ${path}`]
      if (!handler) throw new Error(`Chamada inesperada: ${init?.method ?? 'GET'} ${path}`)
      const { status = 200, body } = handler(init)
      return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
      })
    }),
  )
}

function renderProfile() {
  return render(
    <MemoryRouter initialEntries={['/empresa/perfil']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Perfil da empresa', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('mostra verificação, números, cadastro e só as vagas encerradas no histórico', async () => {
    mockApi()
    renderProfile()

    expect(await screen.findByRole('heading', { level: 1, name: 'Mercado Bom' })).toBeInTheDocument()
    expect(screen.getByText('Empresa verificada')).toBeInTheDocument()
    expect(screen.getByText('Total pago').parentElement).toHaveTextContent('R$ 200,00')
    expect(screen.getByText('Razão social').parentElement).toHaveTextContent('Mercado Bom LTDA')
    expect(screen.getAllByText(/11\.222\.333\/0001-81/).length).toBeGreaterThan(0)
    const links = await screen.findAllByRole('link', { name: 'Inventário de fim de mês' })
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAttribute('href', '/empresa/vagas/9')
  })

  it('salva a apresentação editada', async () => {
    let sent: unknown
    mockApi({
      'PATCH /api/companies/me/': (init) => {
        sent = JSON.parse(String(init?.body))
        return { body: { ...profile, description: 'Rede de mercados de bairro.' } }
      },
    })
    renderProfile()

    await userEvent.click(await screen.findByRole('button', { name: 'Editar apresentação' }))
    await userEvent.type(screen.getByLabelText('Apresentação'), 'Rede de mercados de bairro.')
    await userEvent.click(screen.getByRole('button', { name: 'Salvar' }))

    expect(await screen.findByText('Rede de mercados de bairro.')).toBeInTheDocument()
    expect(sent).toEqual({ description: 'Rede de mercados de bairro.', phone: '' })
  })
})
