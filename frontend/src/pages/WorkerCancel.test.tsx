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

const base = {
  kind: 'assignment',
  id: 31,
  vacancy_id: 7,
  title: 'Carga e descarga',
  company_name: 'Mercado Bom',
  starts_at: '2099-11-03T12:00:00Z',
  ends_at: '2099-11-03T16:00:00Z',
  gross_cents: 10000,
  net_cents: 9700,
  status: 'CONFIRMADA',
  status_label: 'Confirmada',
  can_withdraw: false,
  can_check_in: false,
  can_check_out: false,
  can_cancel: true,
  cancel_is_late: false,
  cancel_warning: '',
  check_in_opens_at: '2099-11-03T11:30:00Z',
  check_in_closes_at: '2099-11-03T12:30:00Z',
  check_in_at: null,
  check_out_at: null,
  check_out_auto: false,
}

const empty: Record<string, unknown[]> = {
  waiting: [],
  upcoming: [],
  in_progress: [],
  completed: [],
  closed: [],
}

function jobsWith(groups: Record<string, unknown[]>) {
  return () => ({ body: { groups: { ...empty, ...groups } } })
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

describe('Cancelar participação (US72)', () => {
  it('cancela com antecedência, avisando que não há penalidade', async () => {
    let done = false
    const cancelled = {
      ...base,
      status: 'CANCELADA_PRESTADOR',
      status_label: 'Cancelada pelo prestador',
      can_cancel: false,
    }
    const fetchMock = mockApi({
      ...session,
      'GET /api/workers/me/jobs/': () =>
        done ? jobsWith({ closed: [cancelled] })() : jobsWith({ upcoming: [base] })(),
      'POST /api/assignments/31/cancel-by-worker/': () => {
        done = true
        return { body: cancelled }
      },
    })
    renderJobs()

    await userEvent.click(await screen.findByRole('button', { name: 'Cancelar participação' }))
    expect(screen.getByText('Cancelando agora você não sofre penalidade.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes('cancel'))).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar cancelamento' }))

    expect(await screen.findByText('Cancelada pelo prestador')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelar participação' })).not.toBeInTheDocument()
  })

  it('mostra o aviso de bloqueio no cancelamento tardio antes de confirmar', async () => {
    const warning = 'Cancelando agora você fica 7 dias sem poder se candidatar.'
    const late = { ...base, cancel_is_late: true, cancel_warning: warning }
    mockApi({ ...session, 'GET /api/workers/me/jobs/': jobsWith({ upcoming: [late] }) })
    renderJobs()

    await userEvent.click(await screen.findByRole('button', { name: 'Cancelar participação' }))

    expect(screen.getByText(warning)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmar cancelamento' })).toBeInTheDocument()
  })

  it('"Voltar" desfaz a confirmação sem chamar a API', async () => {
    const fetchMock = mockApi({
      ...session,
      'GET /api/workers/me/jobs/': jobsWith({ upcoming: [base] }),
    })
    renderJobs()

    await userEvent.click(await screen.findByRole('button', { name: 'Cancelar participação' }))
    await userEvent.click(screen.getByRole('button', { name: 'Voltar' }))

    expect(screen.getByRole('button', { name: 'Cancelar participação' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes('cancel'))).toBe(false)
  })

  it('mostra o erro da API quando o cancelamento é recusado', async () => {
    mockApi({
      ...session,
      'GET /api/workers/me/jobs/': jobsWith({ upcoming: [base] }),
      'POST /api/assignments/31/cancel-by-worker/': () => ({
        status: 409,
        body: { detail: 'Transição não permitida em Assignment: EM_EXECUCAO → CANCELADA_PRESTADOR.' },
      }),
    })
    renderJobs()

    await userEvent.click(await screen.findByRole('button', { name: 'Cancelar participação' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar cancelamento' }))

    expect(await screen.findByText(/Transição não permitida/)).toBeInTheDocument()
  })

  it('não mostra o botão em alocação em execução nem em candidatura pendente', async () => {
    const running = {
      ...base,
      status: 'EM_EXECUCAO',
      status_label: 'Em execução',
      can_cancel: false,
      can_check_out: true,
    }
    const pending = {
      kind: 'application',
      id: 9,
      vacancy_id: 8,
      title: 'Outra vaga',
      company_name: 'Mercado Bom',
      starts_at: '2099-11-04T12:00:00Z',
      ends_at: '2099-11-04T16:00:00Z',
      gross_cents: 10000,
      net_cents: 9700,
      status: 'PENDENTE',
      status_label: 'Pendente',
      can_withdraw: true,
    }
    mockApi({
      ...session,
      'GET /api/workers/me/jobs/': jobsWith({ in_progress: [running], waiting: [pending] }),
    })
    renderJobs()

    expect(await screen.findByRole('button', { name: 'Desistir' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelar participação' })).not.toBeInTheDocument()
  })
})
