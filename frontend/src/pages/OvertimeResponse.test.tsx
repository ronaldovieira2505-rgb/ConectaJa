import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
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

const session: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'João', email: 'j@example.com', role: 'WORKER', verification_status: 'APROVADO' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
}

const request = {
  id: 9,
  assignment_id: 31,
  minutes: 60,
  minutes_label: '1 h',
  amount_cents: 3000,
  net_cents: 2910,
  status: 'AGUARDANDO_PRESTADOR',
  status_label: 'Aguardando prestador',
  created_at: '2026-11-03T15:00:00Z',
  expires_at: '2026-11-03T15:15:00Z',
  responded_at: null,
}

const running = {
  kind: 'assignment',
  id: 31,
  vacancy_id: 7,
  title: 'Carga e descarga',
  company_name: 'Mercado Bom',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  gross_cents: 10000,
  net_cents: 9700,
  status: 'EM_EXECUCAO',
  status_label: 'Em execução',
  can_withdraw: false,
  can_check_in: false,
  can_check_out: true,
  check_in_at: '2026-11-03T12:00:00Z',
  check_out_at: null,
  check_out_auto: false,
  overtime: request,
  can_respond_overtime: true,
  extended_until: null,
}

function jobs(item: object) {
  return () => ({
    body: { groups: { waiting: [], upcoming: [], in_progress: [item], completed: [], closed: [] } },
  })
}

function renderJobs() {
  render(
    <MemoryRouter initialEntries={['/meus-trabalhos']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Responder à hora extra (US53)', () => {
  it('mostra as horas, o bruto e o líquido e aceita', async () => {
    let accepted = false
    const accepted_item = {
      ...running,
      overtime: { ...request, status: 'ACEITO', status_label: 'Aceito' },
      can_respond_overtime: false,
      extended_until: '2026-11-03T17:00:00Z',
    }
    const fetchMock = mockApi({
      ...session,
      'GET /api/workers/me/jobs/': () => (accepted ? jobs(accepted_item)() : jobs(running)()),
      'POST /api/overtime/9/accept/': () => {
        accepted = true
        return { body: { ...request, status: 'ACEITO' } }
      },
    })
    renderJobs()

    expect(await screen.findByText(/A empresa pediu/)).toHaveTextContent(
      /1 h a mais\. Valor bruto R\$\s?30,00 · você recebe R\$\s?29,10/,
    )
    expect(screen.getByText('Recusar não gera penalidade.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Aceitar hora extra' }))

    expect(await screen.findByText('Hora extra aceita. A empresa foi avisada.')).toBeInTheDocument()
    expect(screen.getByText(/Hora extra aceita: 1 h a mais, você recebe R\$\s?29,10\. O turno agora termina às/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Aceitar hora extra' })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([p]) => p === '/api/overtime/9/accept/')).toBe(true)
  })

  it('recusa sem penalidade', async () => {
    let declined = false
    mockApi({
      ...session,
      'GET /api/workers/me/jobs/': () =>
        declined
          ? jobs({ ...running, overtime: { ...request, status: 'RECUSADO' }, can_respond_overtime: false })()
          : jobs(running)(),
      'POST /api/overtime/9/decline/': () => {
        declined = true
        return { body: { ...request, status: 'RECUSADO' } }
      },
    })
    renderJobs()

    await userEvent.click(await screen.findByRole('button', { name: 'Recusar' }))
    expect(await screen.findByText('Hora extra recusada. A empresa foi avisada.')).toBeInTheDocument()
    expect(screen.getByText('Você recusou a hora extra.')).toBeInTheDocument()
  })

  it('mostra o erro quando o pagamento falha e mantém os botões', async () => {
    mockApi({
      ...session,
      'GET /api/workers/me/jobs/': jobs(running),
      'POST /api/overtime/9/accept/': () => ({
        status: 409,
        body: { detail: 'Não foi possível confirmar o pagamento da hora extra. O turno não foi estendido.' },
      }),
    })
    renderJobs()

    await userEvent.click(await screen.findByRole('button', { name: 'Aceitar hora extra' }))
    expect(await screen.findByText(/O turno não foi estendido\./)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Aceitar hora extra' })).toBeInTheDocument()
  })

  it('esconde os botões de um pedido expirado', async () => {
    mockApi({
      ...session,
      'GET /api/workers/me/jobs/': jobs({
        ...running,
        overtime: { ...request, status: 'EXPIRADO' },
        can_respond_overtime: false,
      }),
    })
    renderJobs()

    expect(await screen.findByText('Carga e descarga')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Aceitar hora extra' })).not.toBeInTheDocument()
    expect(screen.queryByText(/A empresa pediu/)).not.toBeInTheDocument()
  })
})
