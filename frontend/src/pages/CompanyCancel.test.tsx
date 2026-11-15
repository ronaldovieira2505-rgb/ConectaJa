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
  status: 'PUBLICADA',
  status_label: 'Publicada',
}

const team = {
  positions: 1,
  filled_positions: 1,
  team_complete: true,
  free_cancel_minutes_before: 1440,
  candidates: [],
  team: [{ id: 5, first_name: 'Maria', phone: '11999998888', status: 'CONFIRMADA', status_label: 'Confirmada' }],
}

const session: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
  'GET /api/vacancies/7/': () => ({ body: vacancy }),
  'GET /api/vacancies/7/candidates/': () => ({ body: team }),
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

describe('Cancelamento pela empresa (US71)', () => {
  it('cancela um prestador confirmado informando o motivo', async () => {
    const calls = mockApi({
      ...session,
      'POST /api/assignments/5/cancel-by-company/': () => ({
        body: { id: 5, status: 'CANCELADA_EMPRESA', status_label: 'Cancelada pela empresa' },
      }),
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Cancelar Maria' }))
    await userEvent.type(screen.getByLabelText('Motivo do cancelamento'), 'Mudança de planos')
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar cancelamento' }))

    expect(await screen.findByText(/Turno cancelado/)).toBeInTheDocument()
    const call = calls.find((c) => c.key === 'POST /api/assignments/5/cancel-by-company/')
    expect(JSON.parse(call?.body ?? '{}')).toEqual({ reason: 'Mudança de planos' })
  })

  it('exige o motivo e não chama a API sem ele', async () => {
    const calls = mockApi(session)
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Cancelar Maria' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar cancelamento' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Informe o motivo do cancelamento.')
    expect(calls.some((c) => c.key.startsWith('POST'))).toBe(false)
  })

  it('mostra a mensagem de prazo quando faltam menos de 24 h', async () => {
    const message = 'Cancelamentos só podem ser feitos até 24 h antes do início. Fale com o suporte.'
    mockApi({
      ...session,
      'POST /api/assignments/5/cancel-by-company/': () => ({ status: 409, body: { detail: message } }),
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Cancelar Maria' }))
    await userEvent.type(screen.getByLabelText('Motivo do cancelamento'), 'Imprevisto')
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar cancelamento' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
  })

  it('cancela a vaga inteira após confirmar com o motivo', async () => {
    const calls = mockApi({
      ...session,
      'POST /api/vacancies/7/cancel/': () => ({
        body: { ...vacancy, status: 'CANCELADA', status_label: 'Cancelada', retained_cents: 0 },
      }),
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Cancelar vaga inteira' }))
    await userEvent.type(screen.getByLabelText('Motivo do cancelamento'), 'Obra suspensa')
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar cancelamento da vaga' }))

    expect(await screen.findByText(/Vaga cancelada\. O valor foi estornado/)).toBeInTheDocument()
    const call = calls.find((c) => c.key === 'POST /api/vacancies/7/cancel/')
    expect(JSON.parse(call?.body ?? '{}')).toEqual({ reason: 'Obra suspensa' })
  })

  it('não oferece "Cancelar vaga inteira" sem prestador aprovado', async () => {
    mockApi({
      ...session,
      'GET /api/vacancies/7/': () => ({ body: { ...vacancy, filled_positions: 0 } }),
      'GET /api/vacancies/7/candidates/': () => ({
        body: { ...team, filled_positions: 0, team_complete: false, team: [] },
      }),
    })
    renderPage()

    expect(await screen.findByRole('button', { name: 'Remover anúncio' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelar vaga inteira' })).not.toBeInTheDocument()
  })
})
