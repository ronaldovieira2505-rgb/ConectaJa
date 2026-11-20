import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

type Handler = () => { status?: number; body?: unknown }

function mockApi(handlers: Record<string, Handler>) {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${path}`
      const handler = handlers[key]
      if (!handler) throw new Error(`Chamada inesperada: ${key}`)
      const { status = 200, body } = handler()
      return Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) })
    }),
  )
}

afterEach(() => vi.unstubAllGlobals())

const photos = Array.from({ length: 6 }, (_, i) => ({
  id: i + 1,
  caption: `Trabalho ${i + 1}`,
  url: `/api/workers/portfolio/${i + 1}/file/`,
}))

function setup(portfolio: unknown[]) {
  mockApi({
    'GET /api/auth/me/': () => ({
      body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
    }),
    'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
    'GET /api/vacancies/7/': () => ({
      body: {
        id: 7, title: 'Pintura', category: 'OUTROS', category_label: 'Outros', description: 'x',
        street: '', city: '', state: '', latitude: '0', longitude: '0',
        starts_at: '2026-11-25T12:00:00Z', ends_at: '2026-11-25T16:00:00Z',
        pay_per_person_cents: 10000, positions: 1, filled_positions: 0, total_cents: 10000,
        retained_cents: 10000, status: 'PUBLICADA', status_label: 'Publicada', photo_url: null,
      },
    }),
    'GET /api/vacancies/7/candidates/': () => ({
      body: {
        positions: 1, filled_positions: 0, team_complete: false, team: [],
        candidates: [
          { id: 11, name: 'Ana', photo_url: null, verified: true, completed_shifts: 1,
            applied_at: '2026-11-20T12:00:00Z', portfolio },
        ],
      },
    }),
  })
  render(
    <MemoryRouter initialEntries={['/empresa/vagas/7']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Fotos do candidato (US41)', () => {
  it('mostra 4 miniaturas e +N, abre a foto grande e passa para a próxima', async () => {
    setup(photos)
    const user = userEvent.setup()

    const thumbs = await screen.findByRole('list', { name: 'Trabalhos anteriores de Ana' })
    expect(within(thumbs).getAllByRole('button')).toHaveLength(5)
    expect(within(thumbs).getByRole('button', { name: 'Ver mais 2 fotos' })).toHaveTextContent('+2')

    await user.click(within(thumbs).getByRole('button', { name: /Ver foto 1 de 6/ }))
    const dialog = screen.getByRole('dialog', { name: 'Trabalhos anteriores de Ana' })
    expect(within(dialog).getByAltText('Trabalho 1')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Próxima' }))
    expect(within(dialog).getByAltText('Trabalho 2')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Fechar' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('candidato sem fotos não mostra nada', async () => {
    setup([])

    expect(await screen.findByText('Ana')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Trabalhos anteriores de Ana' })).not.toBeInTheDocument()
  })
})
