import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

type Handler = (init?: RequestInit) => { status?: number; body?: unknown }

function mockApi(handlers: Record<string, Handler>) {
  const calls: { key: string; body?: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${path}`
      calls.push({ key, body: init?.body ? JSON.parse(String(init.body)) : undefined })
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

const worker: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 2, name: 'Maria', email: 'm@x.com', role: 'WORKER', verification_status: 'APROVADO' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
}

const company: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
}

const JOBS = 'GET /api/workers/me/jobs/'
const RESPOND = 'POST /api/assignments/31/contest-response/'
const PENDING = 'GET /api/company/assignments/pending/'
const SENT_AT = '2026-11-03T17:30:00Z' // 14:30 em Brasília
const TEXT = 'Cumpri o horário inteiro e o encarregado assinou a minha saída.'

const base = {
  kind: 'assignment',
  id: 31,
  vacancy_id: 7,
  title: 'Carga e descarga',
  company_name: 'Mercado Bom',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  gross_cents: 10000,
  net_cents: 9700,
  status: 'CONTESTADA',
  status_label: 'Contestada',
  can_withdraw: false,
  can_check_in: false,
  can_check_out: false,
  can_cancel: false,
  check_in_at: '2026-11-03T12:05:00Z',
  check_out_at: '2026-11-03T16:00:00Z',
  check_out_auto: false,
  contest_reason: 'Saiu duas horas antes',
  can_respond_to_contest: true,
  contest_response: '',
  contest_response_at: null,
}

function jobs(item: unknown): Handler {
  return () => ({
    body: { groups: { waiting: [], upcoming: [], in_progress: [item], completed: [], closed: [] } },
  })
}

function renderAt(path: string) {
  return render(
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

describe('Responder à contestação (US58)', () => {
  it('mostra o motivo da empresa e o campo "Sua versão"', async () => {
    mockApi({ ...worker, [JOBS]: jobs(base) })
    renderAt('/meus-trabalhos')

    expect(await screen.findByText(/Saiu duas horas antes/)).toBeInTheDocument()
    expect(screen.getByLabelText('Sua versão')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar resposta' })).toBeInTheDocument()
  })

  it.each([['vazio', ''], ['curto', 'curto'], ['longo', 'x'.repeat(1001)]])(
    'texto %s mostra o erro e não envia nada',
    async (_name, text) => {
      const calls = mockApi({ ...worker, [JOBS]: jobs(base) })
      renderAt('/meus-trabalhos')

      const field = await screen.findByLabelText('Sua versão')
      if (text) {
        await userEvent.click(field)
        await userEvent.paste(text)
      }
      await userEvent.click(screen.getByRole('button', { name: 'Enviar resposta' }))

      expect(
        await screen.findByText('A sua versão deve ter de 10 a 1.000 caracteres.'),
      ).toBeInTheDocument()
      expect(calls.some((c) => c.key === RESPOND)).toBe(false)
    },
  )

  it('envia a resposta e passa a mostrar "Sua versão, enviada em dd/mm às hh:mm"', async () => {
    let sent = false
    const calls = mockApi({
      ...worker,
      [JOBS]: () =>
        jobs(
          sent
            ? {
                ...base,
                can_respond_to_contest: false,
                contest_response: TEXT,
                contest_response_at: SENT_AT,
              }
            : base,
        )(),
      [RESPOND]: () => {
        sent = true
        return { body: { id: 31 } }
      },
    })
    renderAt('/meus-trabalhos')

    await userEvent.type(await screen.findByLabelText('Sua versão'), TEXT)
    await userEvent.click(screen.getByRole('button', { name: 'Enviar resposta' }))

    expect(await screen.findByText(/Sua versão, enviada em 03\/11 às 14:30/)).toBeInTheDocument()
    expect(screen.getByText(new RegExp(TEXT))).toBeInTheDocument()
    expect(calls.find((c) => c.key === RESPOND)?.body).toEqual({ text: TEXT })
    expect(screen.queryByLabelText('Sua versão')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Enviar resposta' })).not.toBeInTheDocument()
  })

  it('depois de responder não há campo nem botão para enviar de novo', async () => {
    mockApi({
      ...worker,
      [JOBS]: jobs({
        ...base,
        can_respond_to_contest: false,
        contest_response: TEXT,
        contest_response_at: SENT_AT,
      }),
    })
    renderAt('/meus-trabalhos')

    expect(await screen.findByText(/Sua versão, enviada em 03\/11 às 14:30/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Sua versão')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Enviar resposta' })).not.toBeInTheDocument()
  })

  it('depois da decisão do admin a resposta continua visível e não há como responder', async () => {
    mockApi({
      ...worker,
      [JOBS]: jobs({
        ...base,
        status: 'APROVADA',
        status_label: 'Aprovada',
        can_respond_to_contest: false,
        contest_response: TEXT,
        contest_response_at: SENT_AT,
      }),
    })
    renderAt('/meus-trabalhos')

    expect(await screen.findByText(/Sua versão, enviada em 03\/11 às 14:30/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Enviar resposta' })).not.toBeInTheDocument()
  })

  it('mostra o erro da API quando o envio é recusado', async () => {
    mockApi({
      ...worker,
      [JOBS]: jobs(base),
      [RESPOND]: () => ({
        status: 409,
        body: { detail: 'Você já enviou a sua versão. A resposta não pode ser alterada.' },
      }),
    })
    renderAt('/meus-trabalhos')

    await userEvent.type(await screen.findByLabelText('Sua versão'), TEXT)
    await userEvent.click(screen.getByRole('button', { name: 'Enviar resposta' }))

    expect(await screen.findByText(/Você já enviou a sua versão\./)).toBeInTheDocument()
  })

  it('a empresa vê a resposta do prestador no detalhe da alocação contestada', async () => {
    mockApi({
      ...company,
      [PENDING]: () => ({
        body: {
          results: [],
          contested: [
            {
              id: 31,
              vacancy_id: 7,
              vacancy_title: 'Carga e descarga',
              worker_first_name: 'Maria',
              contest_reason: 'Saiu duas horas antes',
              contest_response: TEXT,
              contest_response_at: SENT_AT,
            },
          ],
        },
      }),
    })
    renderAt('/empresa/confirmar-presenca')

    expect(await screen.findByText(/Versão do prestador, enviada em 03\/11 às 14:30/)).toBeInTheDocument()
    expect(screen.getByText(new RegExp(TEXT))).toBeInTheDocument()
    expect(screen.getByText(/Saiu duas horas antes/)).toBeInTheDocument()
  })
})
