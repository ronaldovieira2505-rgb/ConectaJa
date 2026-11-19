import { render, screen } from '@testing-library/react'
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

const vacancy = {
  id: 7,
  title: 'Carga e descarga',
  category_label: 'Carga e descarga',
  description: 'Descarregar caminhão',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  pay_per_person_cents: 10000,
  positions: 1,
  filled_positions: 0,
  total_cents: 10000,
  retained_cents: 10000,
  status: 'PUBLICADA',
  status_label: 'Publicada',
}

const candidate = {
  id: 11,
  name: 'Maria',
  photo_url: '/api/applications/11/photo/',
  verified: true,
  completed_shifts: 3,
  applied_at: '2026-11-01T12:00:00Z',
}

const session: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
  'GET /api/vacancies/7/': () => ({ body: vacancy }),
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/empresa/vagas/7']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Candidatos da vaga', () => {
  it('lista o candidato sem dados sensíveis', async () => {
    mockApi({
      ...session,
      'GET /api/vacancies/7/candidates/': () => ({
        body: { positions: 1, filled_positions: 0, team_complete: false, candidates: [candidate], team: [] },
      }),
    })
    renderPage()

    expect(await screen.findByText('Maria')).toBeInTheDocument()
    expect(screen.getByText('Verificado')).toBeInTheDocument()
    expect(screen.getByText(/3 turnos concluídos/)).toBeInTheDocument()
    expect(screen.getByAltText('Foto de Maria')).toBeInTheDocument()
    expect(screen.queryByText(/CPF|PIX/)).not.toBeInTheDocument()
  })

  it('aprova e mostra o contato liberado da equipe', async () => {
    let approved = false
    const calls = mockApi({
      ...session,
      'GET /api/vacancies/7/candidates/': () => ({
        body: approved
          ? {
              positions: 1,
              filled_positions: 1,
              team_complete: true,
              candidates: [],
              team: [{ id: 5, first_name: 'Maria', phone: '11999998888', status: 'CONFIRMADA', status_label: 'Confirmada' }],
            }
          : { positions: 1, filled_positions: 0, team_complete: false, candidates: [candidate], team: [] },
      }),
      'POST /api/applications/11/approve/': () => {
        approved = true
        return { body: { application_id: 11, status: 'APROVADA' } }
      },
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Aprovar' }))

    expect(await screen.findByText(/11999998888/)).toBeInTheDocument()
    expect(calls).toContain('POST /api/applications/11/approve/')
  })

  it('desabilita "Aprovar" quando a equipe está completa', async () => {
    mockApi({
      ...session,
      'GET /api/vacancies/7/candidates/': () => ({
        body: { positions: 1, filled_positions: 1, team_complete: true, candidates: [candidate], team: [] },
      }),
    })
    renderPage()

    expect(await screen.findByRole('button', { name: 'Equipe completa' })).toBeDisabled()
  })

  it('recusa o candidato', async () => {
    let rejected = false
    const calls = mockApi({
      ...session,
      'GET /api/vacancies/7/candidates/': () => ({
        body: {
          positions: 1,
          filled_positions: 0,
          team_complete: false,
          candidates: rejected ? [] : [candidate],
          team: [],
        },
      }),
      'POST /api/applications/11/reject/': () => {
        rejected = true
        return { body: { application_id: 11, status: 'RECUSADA' } }
      },
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Recusar' }))

    expect(await screen.findByText('Nenhum candidato pendente.')).toBeInTheDocument()
    expect(calls).toContain('POST /api/applications/11/reject/')
  })

  it('mostra o erro da API ao aprovar', async () => {
    mockApi({
      ...session,
      'GET /api/vacancies/7/candidates/': () => ({
        body: { positions: 1, filled_positions: 0, team_complete: false, candidates: [candidate], team: [] },
      }),
      'POST /api/applications/11/approve/': () => ({
        status: 409,
        body: { detail: 'Não há posição livre nesta vaga.' },
      }),
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Aprovar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Não há posição livre nesta vaga.')
  })

  it('mostra nota média, quantidade e as avaliações recentes ao expandir', async () => {
    const rated = {
      ...candidate,
      no_shows_30d: 1,
      rating_avg: 4.8,
      rating_count: 9,
      recent_reviews: [
        { rating: 5, comment: 'Pontual e atencioso', created_at: '2026-10-20T15:00:00Z', company_name: 'Padaria do Zé' },
        { rating: 4, comment: '', created_at: '2026-10-10T15:00:00Z', company_name: 'Mercado Sol' },
      ],
    }
    mockApi({
      ...session,
      'GET /api/vacancies/7/candidates/': () => ({
        body: { positions: 1, filled_positions: 0, team_complete: false, candidates: [rated], team: [] },
      }),
    })
    renderPage()

    expect(await screen.findByText(/★ 4,8 · 9 turnos avaliados/)).toBeInTheDocument()
    expect(screen.getByText(/1 falta nos últimos 30 dias/)).toBeInTheDocument()
    expect(screen.queryByText('Padaria do Zé', { exact: false })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Ver avaliações de Maria/ }))

    expect(screen.getByText('Pontual e atencioso')).toBeInTheDocument()
    expect(screen.getByText(/Padaria do Zé/)).toBeInTheDocument()
    expect(screen.getByText(/Mercado Sol/)).toBeInTheDocument()
    expect(screen.getByText(/20\/10\/2026/)).toBeInTheDocument()
  })

  it('mostra "Novo na plataforma" para candidato sem avaliações', async () => {
    mockApi({
      ...session,
      'GET /api/vacancies/7/candidates/': () => ({
        body: {
          positions: 1,
          filled_positions: 0,
          team_complete: false,
          candidates: [{ ...candidate, no_shows_30d: 0, rating_avg: null, rating_count: 0, recent_reviews: [] }],
          team: [],
        },
      }),
    })
    renderPage()

    expect(await screen.findByText('Novo na plataforma')).toBeInTheDocument()
    expect(screen.getByText(/0 faltas nos últimos 30 dias/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /avaliações/ })).not.toBeInTheDocument()
  })
})
