import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

type Reply = { status?: number; body?: unknown }

function mockApi(handlers: Record<string, () => Reply>) {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${path}`
      const handler = handlers[key]
      if (!handler) throw new Error(`Chamada inesperada: ${key}`)
      const { status = 200, body } = handler()
      return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
      })
    }),
  )
}

function renderHome() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

const anonymous = () => ({ status: 403, body: { detail: 'Não autenticado' } })

const vacancy = {
  id: 7,
  title: 'Carga e descarga no Centro',
  company_name: 'Empresa 1',
  category: 'CARGA_DESCARGA',
  category_label: 'Carga e descarga',
  starts_at: '2026-11-20T12:00:00+00:00',
  ends_at: '2026-11-20T16:00:00+00:00',
  district: 'Centro',
  city: 'São Paulo',
  state: 'SP',
  gross_cents: 10000,
  fee_percent: 3,
  fee_cents: 300,
  net_cents: 9700,
  remaining_positions: 2,
  payment_guaranteed: true,
  urgent: false,
  distance_km: null,
}

describe('Página inicial', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('apresenta a proposta ao visitante e leva aos dois cadastros e à busca', async () => {
    mockApi({
      'GET /api/auth/me/': anonymous,
      'GET /api/vacancies/': () => ({ body: { results: [] } }),
    })

    renderHome()

    expect(
      await screen.findByRole('heading', { level: 1, name: /pagamento garantido/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver vagas abertas' })).toHaveAttribute('href', '/vagas')
    expect(screen.getByRole('link', { name: 'Cadastrar minha empresa' })).toHaveAttribute(
      'href',
      '/cadastro/empresa',
    )
    expect(screen.getByRole('link', { name: 'Quero trabalhar' })).toHaveAttribute(
      'href',
      '/cadastro/prestador',
    )
  })

  it('mostra as vagas publicadas com o valor líquido do prestador', async () => {
    mockApi({
      'GET /api/auth/me/': anonymous,
      'GET /api/vacancies/': () => ({ body: { results: [vacancy] } }),
    })

    renderHome()

    const card = await screen.findByRole('link', { name: /Carga e descarga no Centro/ })
    expect(card).toHaveAttribute('href', '/vagas/7')
    expect(card).toHaveTextContent('R$ 97,00')
    expect(screen.getByText(/1 vaga aberta agora/)).toBeInTheDocument()
  })

  it('continua de pé quando a busca de vagas falha', async () => {
    mockApi({
      'GET /api/auth/me/': anonymous,
      'GET /api/vacancies/': () => ({ status: 500, body: {} }),
    })

    renderHome()

    expect(await screen.findByRole('heading', { name: /três passos/i })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Vagas abertas' })).not.toBeInTheDocument()
  })
})
