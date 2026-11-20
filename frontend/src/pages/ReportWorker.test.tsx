import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

type Handler = (init?: RequestInit) => { status?: number; body?: unknown }

function mockApi(handlers: Record<string, Handler>) {
  const calls: { key: string; body?: string }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${path}`
      calls.push({ key, body: init?.body as string | undefined })
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
  starts_at: '2026-11-20T12:00:00Z',
  ends_at: '2026-11-20T16:00:00Z',
  pay_per_person_cents: 10000,
  positions: 1,
  filled_positions: 1,
  total_cents: 10000,
  retained_cents: 10000,
  status: 'EM_ANDAMENTO',
  status_label: 'Em andamento',
}

const team = {
  positions: 1,
  filled_positions: 1,
  team_complete: true,
  free_cancel_minutes_before: 1440,
  candidates: [],
  team: [{ id: 5, first_name: 'Maria', phone: '11999998888', status: 'PAGA', status_label: 'Paga' }],
}

const session: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
  'GET /api/vacancies/7/': () => ({ body: vacancy }),
  'GET /api/vacancies/7/candidates/': () => ({ body: team }),
  'GET /api/company/past-workers/?vacancy=7': () => ({ body: { results: [] } }),
  'GET /api/company/assignments/pending/?vacancy=7': () => ({
    body: { results: [], contested: [], arrival_justifications: [] },
  }),
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

afterEach(() => vi.unstubAllGlobals())

describe('Denunciar prestador (US70)', () => {
  it('empresa denuncia um prestador da equipe com os motivos de prestador', async () => {
    const calls = mockApi({
      ...session,
      'POST /api/reports/': () => ({
        status: 201,
        body: { id: 1, status: 'ABERTA', detail: 'Denúncia enviada. A equipe vai analisar.' },
      }),
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Denunciar Maria' }))
    expect(screen.getByLabelText('Dano ou furto')).toBeInTheDocument()
    expect(screen.getByLabelText('Documento ou identidade falsa')).toBeInTheDocument()
    expect(screen.queryByLabelText('Vaga falsa ou golpe')).not.toBeInTheDocument()

    await userEvent.click(screen.getByLabelText('Assédio'))
    await userEvent.type(screen.getByLabelText('O que aconteceu?'), 'Comentários ofensivos à equipe.')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar denúncia' }))

    expect(await screen.findByText('Denúncia enviada. A equipe vai analisar.')).toBeInTheDocument()
    const post = calls.find((c) => c.key === 'POST /api/reports/')
    expect(JSON.parse(post?.body ?? '{}')).toEqual({
      target_type: 'PRESTADOR',
      target_id: 5,
      reason: 'ASSEDIO',
      description: 'Comentários ofensivos à equipe.',
    })
  })

  it('mostra o erro de denúncia já aberta', async () => {
    mockApi({
      ...session,
      'POST /api/reports/': () => ({
        status: 409,
        body: { detail: 'Você já tem uma denúncia aberta sobre este alvo. A equipe ainda está analisando.' },
      }),
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Denunciar Maria' }))
    await userEvent.click(screen.getByLabelText('Comportamento inadequado'))
    await userEvent.type(screen.getByLabelText('O que aconteceu?'), 'Chegou alterado ao turno.')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar denúncia' }))
    expect(await screen.findByText(/já tem uma denúncia aberta/)).toBeInTheDocument()
  })
})
