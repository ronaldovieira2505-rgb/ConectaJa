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

const pending = {
  id: 21,
  vacancy_id: 7,
  vacancy_title: 'Carga e descarga',
  worker_first_name: 'Maria',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  check_in_at: '2026-11-03T12:05:00Z',
  check_out_at: '2026-11-03T16:00:00Z',
  check_out_auto: false,
  check_in_distance_m: 78,
  gross_cents: 10000,
  auto_approve_at: '2026-11-04T16:00:00Z',
  auto_approve_in_seconds: 3600,
  can_contest: true,
}

const company: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
}

const worker: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 2, name: 'Maria', email: 'm@x.com', role: 'WORKER', verification_status: 'APROVADO' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
}

const PENDING = 'GET /api/company/assignments/pending/'

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

describe('Contestar horas (US57)', () => {
  it('pede o motivo e não envia nada quando está vazio', async () => {
    const calls = mockApi({ ...company, [PENDING]: () => ({ body: { results: [pending] } }) })
    renderAt('/empresa/confirmar-presenca')

    await userEvent.click(await screen.findByRole('button', { name: 'Contestar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar contestação' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Informe o motivo da contestação.')
    expect(calls.some((c) => c.key.includes('/contest/'))).toBe(false)
  })

  it('contesta com motivo e remove o item da lista', async () => {
    let contested = false
    const calls = mockApi({
      ...company,
      [PENDING]: () => ({ body: { results: contested ? [] : [pending] } }),
      'POST /api/assignments/21/contest/': () => {
        contested = true
        return { body: { id: 21, status: 'CONTESTADA' } }
      },
    })
    renderAt('/empresa/confirmar-presenca')

    await userEvent.click(await screen.findByRole('button', { name: 'Contestar' }))
    await userEvent.type(screen.getByLabelText('Motivo da contestação'), 'Saiu mais cedo')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar contestação' }))

    expect(await screen.findByText(/Horas contestadas/)).toBeInTheDocument()
    expect(screen.getByText('Nenhuma presença aguardando confirmação.')).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'POST /api/assignments/21/contest/')?.body).toEqual({
      reason: 'Saiu mais cedo',
    })
  })

  it('esconde o botão Contestar quando a janela já passou', async () => {
    mockApi({
      ...company,
      [PENDING]: () => ({ body: { results: [{ ...pending, can_contest: false }] } }),
    })
    renderAt('/empresa/confirmar-presenca')

    expect(
      await screen.findByRole('button', { name: 'Confirmar presença e liberar pagamento' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Contestar' })).not.toBeInTheDocument()
  })

  it('mostra o erro da API ao contestar', async () => {
    mockApi({
      ...company,
      [PENDING]: () => ({ body: { results: [pending] } }),
      'POST /api/assignments/21/contest/': () => ({
        status: 409,
        body: { detail: 'O prazo para contestar as horas já terminou.' },
      }),
    })
    renderAt('/empresa/confirmar-presenca')

    await userEvent.click(await screen.findByRole('button', { name: 'Contestar' }))
    await userEvent.type(screen.getByLabelText('Motivo da contestação'), 'Saiu mais cedo')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar contestação' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'O prazo para contestar as horas já terminou.',
    )
  })

  it('mostra ao prestador o status "Horas contestadas" e o motivo da empresa', async () => {
    const item = {
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
    }
    mockApi({
      ...worker,
      'GET /api/workers/me/jobs/': () => ({
        body: {
          groups: { waiting: [], upcoming: [], in_progress: [item], completed: [], closed: [] },
        },
      }),
    })
    renderAt('/meus-trabalhos')

    expect(await screen.findByText('Horas contestadas')).toBeInTheDocument()
    expect(screen.getByText(/Saiu duas horas antes/)).toBeInTheDocument()
  })
})
