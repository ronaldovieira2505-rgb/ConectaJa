import { render, screen, within } from '@testing-library/react'
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

const workerSession: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Ana', email: 'ana@example.com', role: 'WORKER', verification_status: 'APROVADO' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
  'GET /api/workers/me/jobs/': () => ({
    body: { groups: { waiting: [], upcoming: [], in_progress: [], completed: [], closed: [] } },
  }),
}

const profile = {
  id: 1,
  full_name: 'Ana Paula Ribeiro',
  cpf: '***.456.789-**',
  phone: '****8888',
  verification_status: 'APROVADO',
  profile_steps: [],
  documents: [],
}

describe('Nível do prestador (US65)', () => {
  it('mostra o nível atual e quanto falta para o próximo', async () => {
    mockApi({
      ...workerSession,
      'GET /api/workers/me/': () => ({
        body: {
          ...profile,
          level: {
            code: 'BRONZE',
            label: 'Bronze',
            next: {
              code: 'PRATA',
              label: 'Prata',
              missing: ['4 turnos pagos'],
              summary: 'Faltam 4 turnos pagos para o nível Prata',
            },
          },
        },
      }),
    })
    renderAt('/prestador/perfil')

    expect(await screen.findByText('Nível Bronze')).toBeInTheDocument()
    expect(screen.getByLabelText('Próximo nível')).toHaveTextContent(
      'Faltam 4 turnos pagos para o nível Prata.',
    )
  })

  it('no nível Ouro não mostra próximo nível', async () => {
    mockApi({
      ...workerSession,
      'GET /api/workers/me/': () => ({
        body: { ...profile, level: { code: 'OURO', label: 'Ouro', next: null } },
      }),
    })
    renderAt('/prestador/perfil')

    expect(await screen.findByText('Nível Ouro')).toBeInTheDocument()
    expect(screen.getByLabelText('Próximo nível')).toHaveTextContent('Você está no nível mais alto.')
  })

  it('a empresa vê o selo do nível de cada candidato e da equipe', async () => {
    mockApi({
      'GET /api/auth/me/': () => ({
        body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
      }),
      'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
      'GET /api/vacancies/7/': () => ({
        body: {
          id: 7,
          title: 'Carga e descarga',
          category_label: 'Carga e descarga',
          description: 'Descarregar caminhão',
          starts_at: '2026-11-25T12:00:00Z',
          ends_at: '2026-11-25T16:00:00Z',
          pay_per_person_cents: 10000,
          positions: 2,
          filled_positions: 1,
          total_cents: 20000,
          retained_cents: 20000,
          status: 'PUBLICADA',
          status_label: 'Publicada',
        },
      }),
      'GET /api/vacancies/7/candidates/': () => ({
        body: {
          positions: 2,
          filled_positions: 1,
          team_complete: false,
          free_cancel_minutes_before: 1440,
          candidates: [
            {
              id: 11,
              name: 'Maria',
              photo_url: null,
              verified: true,
              completed_shifts: 16,
              level: 'PRATA',
              level_label: 'Prata',
              applied_at: '2026-11-01T12:00:00Z',
            },
          ],
          team: [
            {
              id: 5,
              first_name: 'João',
              phone: '11999998888',
              status: 'CONFIRMADA',
              status_label: 'Confirmada',
              level: 'OURO',
              level_label: 'Ouro',
            },
          ],
        },
      }),
      'GET /api/company/past-workers/?vacancy=7': () => ({ body: { results: [] } }),
    })
    renderAt('/empresa/vagas/7')

    const maria = (await screen.findByText('Maria')).closest('li') as HTMLElement
    expect(within(maria).getByText('Nível Prata')).toBeInTheDocument()
    const joao = screen.getByText(/João/).closest('li') as HTMLElement
    expect(within(joao).getByText('Nível Ouro')).toBeInTheDocument()
  })
})
