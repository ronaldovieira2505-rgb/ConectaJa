import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import { ratingLabel } from '../api'
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

const workerSession: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: {
      id: 1,
      name: 'João',
      email: 'joao@example.com',
      role: 'WORKER',
      verification_status: 'APROVADO',
    },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
}

const paid = {
  kind: 'assignment',
  id: 31,
  vacancy_id: 7,
  title: 'Carga e descarga',
  company_name: 'Mercado Bom',
  starts_at: '2020-11-03T12:00:00Z',
  ends_at: '2020-11-03T16:00:00Z',
  gross_cents: 10000,
  net_cents: 9700,
  status: 'PAGA',
  status_label: 'Paga',
  can_withdraw: false,
  can_review: true,
  review_deadline: '2099-01-01T00:00:00Z',
  my_review: null,
}

const empty = { waiting: [], upcoming: [], in_progress: [], completed: [], closed: [] }

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

describe('Texto da nota da empresa (US64)', () => {
  it('mostra média com uma casa decimal e a quantidade', () => {
    expect(ratingLabel({ average: 4.6, count: 12 })).toBe('★ 4,6 · 12 avaliações')
    expect(ratingLabel({ average: 5, count: 1 })).toBe('★ 5,0 · 1 avaliação')
  })

  it('sem avaliações, mostra "Sem avaliações ainda"', () => {
    expect(ratingLabel({ average: null, count: 0 })).toBe('Sem avaliações ainda')
    expect(ratingLabel(undefined)).toBe('Sem avaliações ainda')
  })
})

describe('Avaliar empresa (US64)', () => {
  it('envia nota e comentário e passa a mostrar a avaliação feita', async () => {
    let sent: unknown = null
    let done = false
    const reviewed = {
      ...paid,
      can_review: false,
      my_review: { rating: 4, comment: 'Turno organizado' },
    }
    mockApi({
      ...workerSession,
      'GET /api/workers/me/jobs/': () => ({
        body: { groups: { ...empty, completed: [done ? reviewed : paid] } },
      }),
      'POST /api/assignments/31/review-company/': (init) => {
        sent = JSON.parse(String(init?.body))
        done = true
        return { status: 201, body: { id: 1 } }
      },
    })
    renderAt('/meus-trabalhos')

    await userEvent.click(await screen.findByRole('button', { name: 'Avaliar empresa' }))
    expect(screen.getByRole('button', { name: 'Enviar avaliação' })).toBeDisabled()
    await userEvent.click(screen.getByLabelText('4 estrelas'))
    await userEvent.type(screen.getByLabelText('Comentário (opcional)'), 'Turno organizado')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar avaliação' }))

    expect(await screen.findByText(/Você avaliou a empresa: 4 de 5/)).toBeInTheDocument()
    expect(sent).toEqual({ rating: 4, comment: 'Turno organizado' })
    expect(screen.queryByRole('button', { name: 'Avaliar empresa' })).not.toBeInTheDocument()
  })

  it('não mostra o botão quando a alocação não pode ser avaliada', async () => {
    mockApi({
      ...workerSession,
      'GET /api/workers/me/jobs/': () => ({
        body: { groups: { ...empty, completed: [{ ...paid, can_review: false }] } },
      }),
    })
    renderAt('/meus-trabalhos')

    expect(await screen.findByText('Carga e descarga')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Avaliar empresa' })).not.toBeInTheDocument()
  })

  it('mostra o erro da API (por exemplo, prazo encerrado)', async () => {
    mockApi({
      ...workerSession,
      'GET /api/workers/me/jobs/': () => ({ body: { groups: { ...empty, completed: [paid] } } }),
      'POST /api/assignments/31/review-company/': () => ({
        status: 409,
        body: { detail: 'O prazo para avaliar esta alocação terminou.' },
      }),
    })
    renderAt('/meus-trabalhos')

    await userEvent.click(await screen.findByRole('button', { name: 'Avaliar empresa' }))
    await userEvent.click(screen.getByLabelText('5 estrelas'))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar avaliação' }))

    expect(
      await screen.findByText('O prazo para avaliar esta alocação terminou.'),
    ).toBeInTheDocument()
  })
})

describe('Avaliações recebidas pela empresa (US64)', () => {
  it('lista os comentários com o prestador abreviado', async () => {
    mockApi({
      'GET /api/auth/me/': () => ({
        body: { id: 2, name: 'Mercado', email: 'm@example.com', role: 'COMPANY' },
      }),
      'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
      'GET /api/company/reviews/': () => ({
        body: {
          summary: { average: 4.5, count: 2 },
          results: [
            {
              id: 1,
              rating: 5,
              comment: 'Pagamento rápido.',
              created_at: '2026-01-01T10:00:00Z',
              vacancy_title: 'Carga e descarga',
              reviewer: 'Ana S.',
            },
          ],
        },
      }),
    })
    renderAt('/empresa/avaliacoes')

    expect(await screen.findByText('★ 4,5 · 2 avaliações')).toBeInTheDocument()
    expect(screen.getByText('Pagamento rápido.')).toBeInTheDocument()
    expect(screen.getByText('Ana S. · Carga e descarga')).toBeInTheDocument()
  })
})
