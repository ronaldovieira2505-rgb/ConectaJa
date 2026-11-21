import { render, screen, within } from '@testing-library/react'
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
      return Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) })
    }),
  )
  return calls
}

const session: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
}

const reviewable = {
  id: 21,
  vacancy_id: 7,
  vacancy_title: 'Carga e descarga',
  worker_first_name: 'Maria',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  status: 'PAGA',
  status_label: 'Paga',
  review_deadline: '2026-11-10T16:00:00Z',
}

function pending(toReview: object[]) {
  return () => ({ body: { results: [], contested: [], arrival_justifications: [], to_review: toReview } })
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/empresa/confirmar-presenca']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('Avaliar prestador (US63)', () => {
  it('a empresa avalia o turno aprovado com nota e comentário', async () => {
    let reviewed = false
    const calls = mockApi({
      ...session,
      'GET /api/company/assignments/pending/': () => pending(reviewed ? [] : [reviewable])(),
      'POST /api/assignments/21/review/': () => {
        reviewed = true
        return { status: 201, body: { id: 1, rating: 5 } }
      },
    })
    renderPage()

    const item = (await screen.findByText('Maria')).closest('li') as HTMLElement
    expect(within(item).getByText(/avalie até/)).toBeInTheDocument()
    await userEvent.click(within(item).getByRole('button', { name: 'Avaliar Maria' }))
    expect(screen.getByText('Sua nota para Maria')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar avaliação' })).toBeDisabled()

    await userEvent.click(screen.getByLabelText('5 estrelas'))
    await userEvent.type(screen.getByLabelText('Comentário (opcional)'), 'Pontual e cuidadosa.')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar avaliação' }))

    expect(await screen.findByText('Avaliação de Maria enviada. O prestador já pode vê-la.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Avaliar Maria' })).not.toBeInTheDocument()
    const post = calls.find((c) => c.key === 'POST /api/assignments/21/review/')
    expect(JSON.parse(post?.body ?? '{}')).toEqual({ rating: 5, comment: 'Pontual e cuidadosa.' })
  })

  it('mostra o erro da API, por exemplo prazo encerrado', async () => {
    mockApi({
      ...session,
      'GET /api/company/assignments/pending/': pending([reviewable]),
      'POST /api/assignments/21/review/': () => ({
        status: 409,
        body: { detail: 'O prazo para avaliar esta alocação terminou.' },
      }),
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Avaliar Maria' }))
    await userEvent.click(screen.getByLabelText('3 estrelas'))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar avaliação' }))
    expect(await screen.findByText('O prazo para avaliar esta alocação terminou.')).toBeInTheDocument()
  })

  it('sem turnos para avaliar, a seção não aparece', async () => {
    mockApi({ ...session, 'GET /api/company/assignments/pending/': pending([]) })
    renderPage()

    expect(await screen.findByText('Nenhuma presença aguardando confirmação.')).toBeInTheDocument()
    expect(screen.queryByText('Avaliar prestadores')).not.toBeInTheDocument()
  })
})
