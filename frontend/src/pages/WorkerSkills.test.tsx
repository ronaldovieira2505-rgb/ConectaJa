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
      return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
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

afterEach(() => {
  vi.unstubAllGlobals()
})

const steps = [
  { key: 'documentos', label: 'Documentos e selfie', done: true, status: 'EM_ANALISE' },
  { key: 'pix', label: 'Chave PIX', done: true },
  { key: 'habilidades', label: 'Habilidades e experiência', done: false, optional: true },
]

const profile = {
  id: 1,
  full_name: 'Ana Paula Ribeiro',
  cpf: '***.456.789-**',
  phone: '****8888',
  verification_status: 'EM_ANALISE',
  pix_key_type: 'CPF',
  pix_key: '***.456.789-**',
  verification_message: 'Aguardando verificação',
  profile_steps: steps,
  documents: [],
  skills: [],
  bio: '',
}

const workerSession: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Ana', email: 'ana@example.com', role: 'WORKER', verification_status: 'EM_ANALISE' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
  'GET /api/workers/me/jobs/': () => ({
    body: { groups: { waiting: [], upcoming: [], in_progress: [], completed: [], closed: [] } },
  }),
}

describe('Habilidades e experiência do prestador (US08)', () => {
  it('é uma etapa opcional que não impede o "Tudo enviado"', async () => {
    mockApi({ ...workerSession, 'GET /api/workers/me/': () => ({ body: profile }) })

    renderAt('/prestador/perfil')

    const list = await screen.findByRole('list', { name: 'Etapas do perfil' })
    expect(list).toHaveTextContent('3 Habilidades e experiência')
    expect(list).toHaveTextContent('Opcional')
    expect(screen.getByText('Tudo enviado. Avisamos quando a verificação terminar.')).toBeInTheDocument()
  })

  it('salva as categorias e o resumo e mostra no perfil', async () => {
    let sent: unknown
    mockApi({
      ...workerSession,
      'GET /api/workers/me/': () => ({ body: profile }),
      'PATCH /api/workers/me/': (init) => {
        sent = JSON.parse(String(init?.body))
        return {
          body: {
            ...profile,
            skills: [{ value: 'LIMPEZA', label: 'Limpeza' }],
            bio: 'Três anos em limpeza pós-obra.',
          },
        }
      },
    })
    renderAt('/prestador/perfil')
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Editar' }))
    await user.click(screen.getByRole('checkbox', { name: 'Limpeza' }))
    await user.type(screen.getByLabelText('Resumo da sua experiência'), 'Três anos em limpeza pós-obra.')
    await user.click(screen.getByRole('button', { name: 'Salvar' }))

    expect(sent).toEqual({ skills: ['LIMPEZA'], bio: 'Três anos em limpeza pós-obra.' })
    expect(await screen.findByText('Três anos em limpeza pós-obra.')).toBeInTheDocument()
    expect(screen.getByText('Limpeza')).toBeInTheDocument()
  })

  it('mostra o erro do servidor e continua editando', async () => {
    mockApi({
      ...workerSession,
      'GET /api/workers/me/': () => ({ body: profile }),
      'PATCH /api/workers/me/': () => ({
        status: 400,
        body: {
          detail:
            'Não coloque e-mail nem telefone no resumo: o contato só é liberado depois da alocação.',
        },
      }),
    })
    renderAt('/prestador/perfil')
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Editar' }))
    await user.type(screen.getByLabelText('Resumo da sua experiência'), 'zap 11988887777')
    await user.click(screen.getByRole('button', { name: 'Salvar' }))

    expect(await screen.findByText(/Não coloque e-mail nem telefone/, { selector: '.alert' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Salvar' })).toBeInTheDocument()
  })
})

const companySession: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 2, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
  'GET /api/vacancies/7/': () => ({
    body: {
      id: 7,
      title: 'Limpeza pós-obra',
      category: 'LIMPEZA',
      category_label: 'Limpeza',
      description: 'Limpeza geral',
      starts_at: '2026-11-25T12:00:00Z',
      ends_at: '2026-11-25T16:00:00Z',
      pay_per_person_cents: 10000,
      positions: 1,
      filled_positions: 0,
      total_cents: 10000,
      retained_cents: 10000,
      status: 'PUBLICADA',
      status_label: 'Publicada',
    },
  }),
}

describe('Habilidades na lista de candidatos (US08)', () => {
  it('mostra o resumo e destaca a categoria da vaga', async () => {
    mockApi({
      ...companySession,
      'GET /api/vacancies/7/candidates/': () => ({
        body: {
          positions: 1,
          filled_positions: 0,
          team_complete: false,
          candidates: [
            {
              id: 11,
              name: 'Ana',
              photo_url: null,
              verified: true,
              completed_shifts: 3,
              applied_at: '2026-11-20T12:00:00Z',
              bio: 'Três anos em limpeza pós-obra.',
              skills: [
                { value: 'EVENTOS', label: 'Eventos', matches_vacancy: false },
                { value: 'LIMPEZA', label: 'Limpeza', matches_vacancy: true },
              ],
            },
          ],
          team: [],
        },
      }),
    })

    renderAt('/empresa/vagas/7')

    const tags = await screen.findByLabelText('Experiência de Ana')
    expect(within(tags).getByText('Eventos')).toBeInTheDocument()
    expect(within(tags).getByText('Limpeza · categoria da vaga')).toBeInTheDocument()
    expect(screen.getByText('Três anos em limpeza pós-obra.')).toBeInTheDocument()
  })

  it('não mostra campo vazio para candidato sem habilidades', async () => {
    mockApi({
      ...companySession,
      'GET /api/vacancies/7/candidates/': () => ({
        body: {
          positions: 1,
          filled_positions: 0,
          team_complete: false,
          candidates: [
            {
              id: 11,
              name: 'Ana',
              photo_url: null,
              verified: true,
              completed_shifts: 0,
              applied_at: '2026-11-20T12:00:00Z',
              bio: '',
              skills: [],
            },
          ],
          team: [],
        },
      }),
    })

    renderAt('/empresa/vagas/7')

    expect(await screen.findByText('Ana')).toBeInTheDocument()
    expect(screen.queryByLabelText('Experiência de Ana')).not.toBeInTheDocument()
  })
})
