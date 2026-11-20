import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

type Handler = (init?: RequestInit) => { status?: number; body?: unknown }

function mockApi(handlers: Record<string, Handler>) {
  const fetchMock = vi.fn((path: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${path}`
    const handler = handlers[key]
    if (!handler) throw new Error(`Chamada inesperada: ${key}`)
    const { status = 200, body } = handler(init)
    return Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function me(role: 'WORKER' | 'COMPANY' | null): Handler {
  if (role === null) return () => ({ status: 403, body: {} })
  return () => ({
    body: { id: 1, name: 'Fulano', email: 'f@example.com', role, verification_status: 'APROVADO' },
  })
}

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
  description: 'Supermercado de bairro.',
  profile_available: true,
  open_vacancies: [],
  recent_reviews: [],
}

const vacancy = {
  id: 7,
  title: 'Reposição de estoque',
  company_name: 'Mercado Bom',
  category: 'VAREJO',
  category_label: 'Varejo',
  description: 'Repor gôndolas.',
  starts_at: '2026-11-25T12:00:00Z',
  ends_at: '2026-11-25T16:00:00Z',
  district: 'Centro',
  city: 'São Paulo',
  state: 'SP',
  street: 'Rua A',
  number: '1',
  latitude: -23.5,
  longitude: -46.6,
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
  can_apply: false,
  apply_blocker: null,
  my_application: null,
}

function base(role: 'WORKER' | 'COMPANY' | null): Record<string, Handler> {
  return {
    'GET /api/auth/me/': me(role),
    'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
    'GET /api/companies/3/public/': () => ({ body: company }),
    'GET /api/vacancies/7/': () => ({ body: vacancy }),
  }
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

describe('Denunciar vaga ou empresa (US69)', () => {
  it('prestador denuncia a empresa com motivo e descrição', async () => {
    const fetchMock = mockApi({
      ...base('WORKER'),
      'POST /api/reports/': () => ({
        status: 201,
        body: { id: 1, status: 'ABERTA', detail: 'Denúncia enviada. A equipe vai analisar.' },
      }),
    })
    renderAt('/empresas/3')

    await userEvent.click(await screen.findByRole('button', { name: 'Denunciar esta empresa' }))
    await userEvent.click(screen.getByLabelText('Pedido de pagamento por fora'))
    await userEvent.type(screen.getByLabelText('O que aconteceu?'), 'Pediram PIX adiantado.')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar denúncia' }))

    expect(await screen.findByText('Denúncia enviada. A equipe vai analisar.')).toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([p, init]) => p === '/api/reports/' && init?.method === 'POST')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      target_type: 'EMPRESA',
      target_id: 3,
      reason: 'PAGAMENTO_POR_FORA',
      description: 'Pediram PIX adiantado.',
    })
  })

  it('prestador denuncia a vaga', async () => {
    const fetchMock = mockApi({
      ...base('WORKER'),
      'POST /api/reports/': () => ({
        status: 201,
        body: { id: 2, status: 'ABERTA', detail: 'Denúncia enviada. A equipe vai analisar.' },
      }),
    })
    renderAt('/vagas/7')

    await userEvent.click(await screen.findByRole('button', { name: 'Denunciar esta vaga' }))
    await userEvent.click(screen.getByLabelText('Vaga falsa ou golpe'))
    await userEvent.type(screen.getByLabelText('O que aconteceu?'), 'O endereço não existe.')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar denúncia' }))

    expect(await screen.findByText('Denúncia enviada. A equipe vai analisar.')).toBeInTheDocument()
    const call = fetchMock.mock.calls.find(([p, init]) => p === '/api/reports/' && init?.method === 'POST')
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ target_type: 'VAGA', target_id: 7 })
  })

  it('recusa descrição curta sem chamar a API e mostra a denúncia duplicada', async () => {
    const fetchMock = mockApi({
      ...base('WORKER'),
      'POST /api/reports/': () => ({
        status: 409,
        body: { detail: 'Você já tem uma denúncia aberta sobre este alvo. A equipe ainda está analisando.' },
      }),
    })
    renderAt('/empresas/3')

    await userEvent.click(await screen.findByRole('button', { name: 'Denunciar esta empresa' }))
    await userEvent.click(screen.getByLabelText('Outro'))
    await userEvent.type(screen.getByLabelText('O que aconteceu?'), 'curto')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar denúncia' }))
    expect(screen.getByText('Descreva o que aconteceu com pelo menos 10 caracteres.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([p]) => p === '/api/reports/')).toBe(false)
    expect(screen.getByLabelText('O que aconteceu?')).toHaveAttribute('maxLength', '1000')

    await userEvent.type(screen.getByLabelText('O que aconteceu?'), ' demais, agora sim')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar denúncia' }))
    expect(await screen.findByText(/já tem uma denúncia aberta/)).toBeInTheDocument()
  })

  it('visitante sem login vai para o login', async () => {
    mockApi(base(null))
    renderAt('/empresas/3')

    await userEvent.click(await screen.findByRole('button', { name: 'Denunciar esta empresa' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Entrar' })).toBeInTheDocument()
  })

  it('empresa não vê o link', async () => {
    mockApi(base('COMPANY'))
    renderAt('/empresas/3')

    expect(await screen.findByRole('heading', { level: 1, name: 'Mercado Bom' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Denunciar esta empresa' })).not.toBeInTheDocument()
  })
})
