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
      return Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) })
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

afterEach(() => vi.unstubAllGlobals())

const worker = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Ana', email: 'ana@example.com', role: 'WORKER', verification_status: 'APROVADO' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
} satisfies Record<string, Handler>

const profile = {
  id: 1,
  full_name: 'Ana Paula Ribeiro',
  cpf: '***.456.789-**',
  phone: '****8888',
  verification_status: 'APROVADO',
  profile_steps: [],
  documents: [],
  availability: { days: [], periods: [], summary: '' },
}

describe('Disponibilidade (US10)', () => {
  it('o prestador marca dias e faixas e vê o resumo', async () => {
    let sent: unknown
    mockApi({
      ...worker,
      'GET /api/workers/me/': () => ({ body: profile }),
      'GET /api/workers/me/jobs/': () => ({
        body: { groups: { waiting: [], upcoming: [], in_progress: [], completed: [], closed: [] } },
      }),
      'PATCH /api/workers/me/': (init) => {
        sent = JSON.parse(String(init?.body))
        return {
          body: {
            ...profile,
            availability: { days: ['SEG', 'TER'], periods: ['MANHA'], summary: 'Seg, Ter · manhã' },
          },
        }
      },
    })
    renderAt('/prestador/perfil')
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Editar disponibilidade' }))
    await user.click(screen.getByRole('checkbox', { name: 'Segunda' }))
    await user.click(screen.getByRole('checkbox', { name: 'Terça' }))
    await user.click(screen.getByRole('checkbox', { name: 'Manhã (6h–12h)' }))
    await user.click(screen.getByRole('button', { name: 'Salvar disponibilidade' }))

    expect(await screen.findByText('Seg, Ter · manhã')).toBeInTheDocument()
    expect(sent).toEqual({ availability_days: ['SEG', 'TER'], availability_periods: ['MANHA'] })
  })

  it('a busca oferece "Só nos meus horários" para quem marcou disponibilidade', async () => {
    const calls = mockApi({
      ...worker,
      'GET /api/vacancies/': () => ({ body: { results: [], my_schedule_available: true } }),
      'GET /api/vacancies/?my_schedule=1': () => ({ body: { results: [], my_schedule_available: true } }),
    })
    renderAt('/vagas')
    const user = userEvent.setup()

    await user.click(await screen.findByRole('checkbox', { name: 'Só nos meus horários' }))
    await user.click(screen.getByRole('button', { name: 'Buscar' }))

    await screen.findAllByText('Nenhuma vaga com esses filtros')
    expect(calls).toContain('GET /api/vacancies/?my_schedule=1')
  })

  it('sem disponibilidade marcada o filtro não aparece', async () => {
    mockApi({
      ...worker,
      'GET /api/vacancies/': () => ({ body: { results: [], my_schedule_available: false } }),
    })
    renderAt('/vagas')

    expect(await screen.findByText('Nenhuma vaga com esses filtros')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Só nos meus horários' })).not.toBeInTheDocument()
  })
})
