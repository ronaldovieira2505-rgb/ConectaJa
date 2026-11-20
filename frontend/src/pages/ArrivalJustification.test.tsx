import { render, screen, within } from '@testing-library/react'
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

function bodyOf(fetchMock: ReturnType<typeof mockApi>, path: string) {
  const call = fetchMock.mock.calls.find(([p, init]) => p === path && init?.method === 'POST')
  return JSON.parse(String(call?.[1]?.body))
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

const notifications: Handler = () => ({ body: { unread_count: 0, results: [] } })

describe('Prestador: não consigo registrar a chegada (US51)', () => {
  const workerSession: Record<string, Handler> = {
    'GET /api/auth/me/': () => ({
      body: { id: 1, name: 'João', email: 'j@example.com', role: 'WORKER', verification_status: 'APROVADO' },
    }),
    'GET /api/notifications/': notifications,
  }

  const job = {
    kind: 'assignment',
    id: 31,
    vacancy_id: 7,
    title: 'Carga e descarga',
    company_name: 'Mercado Bom',
    starts_at: '2026-11-03T12:00:00Z',
    ends_at: '2026-11-03T16:00:00Z',
    gross_cents: 10000,
    net_cents: 9700,
    status: 'CONFIRMADA',
    status_label: 'Confirmada',
    can_withdraw: false,
    can_check_in: true,
    can_check_out: false,
    check_in_opens_at: '2026-11-03T11:30:00Z',
    check_in_closes_at: '2026-11-03T12:30:00Z',
    check_in_at: null,
    check_out_at: null,
    check_out_auto: false,
    can_justify_arrival: true,
    arrival_justification: null,
  }

  const justification = {
    id: 5,
    reason: 'GPS',
    reason_label: 'GPS não funciona',
    text: 'Galpão sem sinal.',
    status: 'PENDENTE',
    status_label: 'Aguardando a empresa',
    decision_reason: '',
    created_at: '2026-11-03T12:10:00Z',
  }

  function jobs(item: object) {
    return () => ({
      body: { groups: { waiting: [], upcoming: [item], in_progress: [], completed: [], closed: [] } },
    })
  }

  it('envia o motivo e a explicação e mostra que aguarda a empresa', async () => {
    let sent = false
    const fetchMock = mockApi({
      ...workerSession,
      'GET /api/workers/me/jobs/': () =>
        sent
          ? jobs({ ...job, can_justify_arrival: false, arrival_justification: justification })()
          : jobs(job)(),
      'POST /api/assignments/31/arrival-justification/': () => {
        sent = true
        return { body: {} }
      },
    })
    renderAt('/meus-trabalhos')

    await userEvent.click(await screen.findByRole('button', { name: 'Não consigo registrar a chegada' }))
    await userEvent.click(screen.getByLabelText('GPS não funciona'))
    await userEvent.type(screen.getByLabelText(/Explicação/), 'Galpão sem sinal.')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar justificativa' }))

    expect(await screen.findByText(/Aguardando a empresa confirmar a sua chegada/)).toBeInTheDocument()
    expect(screen.getByText('Justificativa enviada. A empresa foi avisada.')).toBeInTheDocument()
    expect(bodyOf(fetchMock, '/api/assignments/31/arrival-justification/')).toEqual({
      reason: 'GPS',
      text: 'Galpão sem sinal.',
    })
    expect(
      screen.queryByRole('button', { name: 'Não consigo registrar a chegada' }),
    ).not.toBeInTheDocument()
  })

  it('exige explicação quando o motivo é "Outro" e limita a 300 caracteres', async () => {
    const fetchMock = mockApi({ ...workerSession, 'GET /api/workers/me/jobs/': jobs(job) })
    renderAt('/meus-trabalhos')

    await userEvent.click(await screen.findByRole('button', { name: 'Não consigo registrar a chegada' }))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar justificativa' }))
    expect(screen.getByText('Escolha o motivo.')).toBeInTheDocument()

    await userEvent.click(screen.getByLabelText('Outro'))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar justificativa' }))
    expect(screen.getByText('Explique o que aconteceu.')).toBeInTheDocument()
    expect(screen.getByLabelText(/Explicação/)).toHaveAttribute('maxLength', '300')
    expect(fetchMock.mock.calls.some(([p]) => String(p).includes('arrival-justification'))).toBe(false)
  })

  it('mostra o motivo quando a empresa recusa', async () => {
    mockApi({
      ...workerSession,
      'GET /api/workers/me/jobs/': jobs({
        ...job,
        can_justify_arrival: false,
        arrival_justification: {
          ...justification,
          status: 'RECUSADA',
          decision_reason: 'Ninguém chegou ao portão.',
        },
      }),
    })
    renderAt('/meus-trabalhos')
    expect(
      await screen.findByText(/Sua justificativa de chegada foi recusada\. Motivo: Ninguém chegou ao portão\./),
    ).toBeInTheDocument()
  })

  it('indica quando o check-in foi confirmado pela empresa', async () => {
    mockApi({
      ...workerSession,
      'GET /api/workers/me/jobs/': () => ({
        body: {
          groups: {
            waiting: [],
            upcoming: [],
            in_progress: [
              {
                ...job,
                status: 'EM_EXECUCAO',
                status_label: 'Em execução',
                can_check_in: false,
                can_check_out: true,
                can_justify_arrival: false,
                check_in_at: '2026-11-03T12:10:00Z',
                check_in_confirmed_by_company: true,
                arrival_justification: { ...justification, status: 'CONFIRMADA' },
              },
            ],
            completed: [],
            closed: [],
          },
        },
      }),
    })
    renderAt('/meus-trabalhos')
    expect(await screen.findByText(/\(confirmado pela empresa\)/)).toBeInTheDocument()
  })
})

describe('Empresa: confirmar chegada sem check-in (US51)', () => {
  const companySession: Record<string, Handler> = {
    'GET /api/auth/me/': () => ({
      body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
    }),
    'GET /api/notifications/': notifications,
  }

  const arrival = {
    id: 5,
    assignment_id: 31,
    vacancy_id: 7,
    vacancy_title: 'Carga e descarga',
    worker_first_name: 'Maria',
    starts_at: '2026-11-03T12:00:00Z',
    ends_at: '2026-11-03T16:00:00Z',
    reason: 'BATERIA',
    reason_label: 'Celular sem bateria',
    text: 'Acabou a bateria no ônibus.',
    created_at: '2026-11-03T12:10:00Z',
  }

  function pendingWith(list: object[]) {
    return () => ({ body: { results: [], contested: [], arrival_justifications: list } })
  }

  it('mostra o pedido e confirma a chegada', async () => {
    let decided = false
    const fetchMock = mockApi({
      ...companySession,
      'GET /api/company/assignments/pending/': () => pendingWith(decided ? [] : [arrival])(),
      'POST /api/assignments/31/arrival-justification/decide/': () => {
        decided = true
        return { body: { status: 'CONFIRMADA' } }
      },
    })
    renderAt('/empresa/confirmar-presenca')

    const item = (await screen.findByText('Maria')).closest('li') as HTMLElement
    expect(within(item).getByText('Celular sem bateria')).toBeInTheDocument()
    expect(within(item).getByText('“Acabou a bateria no ônibus.”')).toBeInTheDocument()
    expect(within(item).getByText('Sem check-in pelo celular')).toBeInTheDocument()

    await userEvent.click(within(item).getByRole('button', { name: 'Confirmar chegada' }))
    expect(await screen.findByText('Chegada confirmada. O turno está em execução.')).toBeInTheDocument()
    expect(bodyOf(fetchMock, '/api/assignments/31/arrival-justification/decide/')).toEqual({
      confirm: true,
      reason: '',
    })
    expect(screen.queryByText('Maria')).not.toBeInTheDocument()
  })

  it('recusa com motivo obrigatório', async () => {
    const fetchMock = mockApi({
      ...companySession,
      'GET /api/company/assignments/pending/': pendingWith([arrival]),
      'POST /api/assignments/31/arrival-justification/decide/': () => ({ body: { status: 'RECUSADA' } }),
    })
    renderAt('/empresa/confirmar-presenca')

    await userEvent.click(await screen.findByRole('button', { name: 'Recusar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Recusar justificativa' }))
    expect(screen.getByText('Informe o motivo da recusa.')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Motivo da recusa'), 'Não veio ao local.')
    await userEvent.click(screen.getByRole('button', { name: 'Recusar justificativa' }))
    expect(await screen.findByText('Justificativa recusada. O prestador foi avisado.')).toBeInTheDocument()
    expect(bodyOf(fetchMock, '/api/assignments/31/arrival-justification/decide/')).toEqual({
      confirm: false,
      reason: 'Não veio ao local.',
    })
  })
})
