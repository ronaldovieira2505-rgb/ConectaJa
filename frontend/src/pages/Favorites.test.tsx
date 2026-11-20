import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

type Handler = (init?: RequestInit) => { status?: number; body?: unknown }

function mockApi(handlers: Record<string, Handler>) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${path}`
      calls.push(key)
      const handler = handlers[key]
      if (!handler) throw new Error(`Chamada inesperada: ${key}`)
      const { status = 200, body } = handler(init)
      return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
      })
    }),
  )
  return calls
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

afterEach(() => {
  vi.unstubAllGlobals()
})

const card = {
  id: 7,
  title: 'Carga e descarga',
  company_name: 'Mercado Bom',
  category: 'CARGA_DESCARGA',
  category_label: 'Carga e descarga',
  starts_at: '2026-11-25T12:00:00Z',
  ends_at: '2026-11-25T16:00:00Z',
  district: 'Sé',
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
  photo_url: null,
  favorite: false,
}

const detail = {
  ...card,
  description: 'Descarregar caminhão',
  street: 'Praça da Sé',
  number: '1',
  complement: '',
  zip_code: '',
  latitude: '-23.550520',
  longitude: '-46.633308',
  can_apply: true,
  apply_blocker: null,
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

const workerUser = {
  id: 1,
  name: 'Ana',
  email: 'ana@example.com',
  role: 'WORKER',
  verification_status: 'APROVADO',
}

const notifications: Handler = () => ({ body: { unread_count: 0, results: [] } })

describe('Favoritos na busca e no detalhe (US18)', () => {
  it('o prestador salva e remove a vaga pelo coração', async () => {
    const calls = mockApi({
      'GET /api/auth/me/': () => ({ body: workerUser }),
      'GET /api/notifications/': notifications,
      'GET /api/vacancies/': () => ({ body: { results: [card] } }),
      'POST /api/vacancies/7/favorite/': () => ({ status: 201, body: { vacancy_id: 7, favorite: true } }),
      'DELETE /api/vacancies/7/favorite/': () => ({ status: 204 }),
    })
    renderAt('/vagas')
    const user = userEvent.setup()

    const heart = await screen.findByRole('button', { name: 'Salvar “Carga e descarga” nos favoritos' })
    expect(heart).toHaveAttribute('aria-pressed', 'false')
    await user.click(heart)

    const saved = await screen.findByRole('button', { name: 'Remover “Carga e descarga” dos favoritos' })
    expect(saved).toHaveAttribute('aria-pressed', 'true')
    await user.click(saved)

    expect(await screen.findByRole('button', { name: /Salvar “Carga e descarga”/ })).toBeInTheDocument()
    expect(calls).toContain('POST /api/vacancies/7/favorite/')
    expect(calls).toContain('DELETE /api/vacancies/7/favorite/')
  })

  it('o visitante vai para o login e, depois de entrar, volta para a vaga', async () => {
    let logged = false
    mockApi({
      'GET /api/auth/me/': () => (logged ? { body: workerUser } : { status: 403, body: {} }),
      'GET /api/notifications/': notifications,
      'GET /api/vacancies/': () => ({ body: { results: [card] } }),
      'GET /api/auth/csrf/': () => ({ body: { csrfToken: 'x' } }),
      'POST /api/auth/login/': () => {
        logged = true
        return { body: workerUser }
      },
      'GET /api/vacancies/7/': () => ({ body: detail }),
    })
    renderAt('/vagas')
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: /Salvar “Carga e descarga”/ }))
    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('E-mail'), 'ana@example.com')
    await user.type(screen.getByLabelText('Senha'), 'senha-forte-123')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Carga e descarga' })).toBeInTheDocument()
  })

  it('a empresa não vê o coração', async () => {
    mockApi({
      'GET /api/auth/me/': () => ({
        body: { id: 2, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
      }),
      'GET /api/notifications/': notifications,
      'GET /api/vacancies/': () => ({ body: { results: [card] } }),
    })
    renderAt('/vagas')

    expect(await screen.findByRole('link', { name: 'Carga e descarga' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /favoritos/ })).not.toBeInTheDocument()
  })

  it('o detalhe mostra o coração preenchido quando a vaga é favorita', async () => {
    mockApi({
      'GET /api/auth/me/': () => ({ body: workerUser }),
      'GET /api/notifications/': notifications,
      'GET /api/vacancies/7/': () => ({ body: { ...detail, favorite: true } }),
    })
    renderAt('/vagas/7')

    expect(
      await screen.findByRole('button', { name: 'Remover “Carga e descarga” dos favoritos' }),
    ).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('Aba "Favoritas" em Meus trabalhos (US18)', () => {
  it('lista as favoritas com os selos de encerrada e lotada e tira a removida', async () => {
    mockApi({
      'GET /api/auth/me/': () => ({ body: workerUser }),
      'GET /api/notifications/': notifications,
      'GET /api/workers/me/favorites/': () => ({
        body: {
          results: [
            { ...card, favorite: true, closed_label: null },
            { ...card, id: 8, title: 'Evento cancelado', favorite: true, closed_label: 'Encerrada' },
            { ...card, id: 9, title: 'Vaga cheia', favorite: true, closed_label: 'Lotada', remaining_positions: 0 },
          ],
        },
      }),
      'DELETE /api/vacancies/7/favorite/': () => ({ status: 204 }),
    })
    renderAt('/meus-trabalhos/favoritas')
    const user = userEvent.setup()

    expect(await screen.findByRole('link', { name: 'Carga e descarga' })).toBeInTheDocument()
    const tabs = screen.getByRole('navigation', { name: 'Abas de Meus trabalhos' })
    expect(within(tabs).getByRole('link', { name: 'Favoritas' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('Encerrada')).toBeInTheDocument()
    expect(screen.getByText('Lotada')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Evento cancelado' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Vaga cheia' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Remover “Carga e descarga” dos favoritos' }))

    expect(await screen.findByText('Evento cancelado')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Carga e descarga' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Vaga cheia' })).toBeInTheDocument()
  })

  it('mostra o aviso quando não há favoritas', async () => {
    mockApi({
      'GET /api/auth/me/': () => ({ body: workerUser }),
      'GET /api/notifications/': notifications,
      'GET /api/workers/me/favorites/': () => ({ body: { results: [] } }),
    })
    renderAt('/meus-trabalhos/favoritas')

    expect(await screen.findByText('Nenhuma vaga salva')).toBeInTheDocument()
  })
})
