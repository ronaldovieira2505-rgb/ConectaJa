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

afterEach(() => {
  vi.unstubAllGlobals()
})

const vacancy = {
  id: 7,
  title: 'Reposição de estoque',
  category: 'VAREJO',
  category_label: 'Varejo',
  description: 'Repor prateleiras',
  street: '',
  city: '',
  state: '',
  latitude: '-23.550520',
  longitude: '-46.633308',
  starts_at: '2026-11-25T12:00:00Z',
  ends_at: '2026-11-25T16:00:00Z',
  pay_per_person_cents: 10000,
  positions: 2,
  filled_positions: 0,
  total_cents: 20000,
  retained_cents: 20000,
  status: 'PUBLICADA',
  status_label: 'Publicada',
  photo_url: null,
}

const session: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
  'GET /api/vacancies/7/': () => ({ body: vacancy }),
  'GET /api/vacancies/7/candidates/': () => ({
    body: { positions: 2, filled_positions: 0, team_complete: false, candidates: [], team: [] },
  }),
}

function list(invitedAna = false) {
  return {
    vacancy_blocker: null,
    max_invites: 20,
    invites_left: invitedAna ? 19 : 20,
    results: [
      {
        worker_id: 3,
        name: 'Ana R.',
        photo_url: null,
        shifts_with_company: 2,
        rating_given: 4.5,
        invited: invitedAna,
        blocker: null,
      },
      {
        worker_id: 4,
        name: 'Bruno C.',
        photo_url: null,
        shifts_with_company: 1,
        rating_given: null,
        invited: false,
        blocker: 'Já se candidatou a esta vaga.',
      },
    ],
  }
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/empresa/vagas/7']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Convidar prestadores (US44)', () => {
  it('lista quem já trabalhou, convida e marca como convidado', async () => {
    let invited = false
    let sent: unknown
    const calls = mockApi({
      ...session,
      'GET /api/company/past-workers/?vacancy=7': () => ({ body: list(invited) }),
      'POST /api/vacancies/7/invite/': (init) => {
        invited = true
        sent = JSON.parse(String(init?.body))
        return { status: 201, body: { worker_id: 3, invited: true } }
      },
    })
    renderPage()
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Convidar prestadores' }))
    const section = screen.getByRole('region', { name: 'Convidar prestadores' })
    expect(await within(section).findByText('Ana R.')).toBeInTheDocument()
    expect(within(section).getByText(/2 turnos com você · Nota que você deu: ★ 4,5/)).toBeInTheDocument()
    expect(within(section).getByText('Já se candidatou a esta vaga.')).toBeInTheDocument()
    expect(within(section).queryByRole('button', { name: 'Convidar Bruno C.' })).not.toBeInTheDocument()

    await user.click(within(section).getByRole('button', { name: 'Convidar Ana R.' }))

    expect(await within(section).findByText('Convidado')).toBeInTheDocument()
    expect(within(section).getByText('Restam 19 de 20 convites para esta vaga.')).toBeInTheDocument()
    expect(sent).toEqual({ worker_id: 3 })
    expect(calls.filter((c) => c === 'POST /api/vacancies/7/invite/')).toHaveLength(1)
  })

  it('vaga que não aceita convites mostra o motivo e desabilita o botão', async () => {
    mockApi({
      ...session,
      'GET /api/company/past-workers/?vacancy=7': () => ({
        body: { ...list(), vacancy_blocker: 'Esta vaga está lotada.' },
      }),
    })
    renderPage()
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Convidar prestadores' }))

    expect(await screen.findByText('Esta vaga está lotada.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Convidar Ana R.' })).toBeDisabled()
  })
})
