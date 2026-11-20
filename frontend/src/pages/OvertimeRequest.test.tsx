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
  status: 'EM_ANDAMENTO',
  status_label: 'Em andamento',
}

const options = [30, 60, 90, 120, 150, 180, 210, 240].map((minutes) => ({
  minutes,
  label: minutes < 60 ? '30 min' : `${Math.floor(minutes / 60)} h${minutes % 60 ? ' 30 min' : ''}`,
  min_amount_cents: (10000 * minutes) / 240,
}))

const member = {
  id: 5,
  first_name: 'Maria',
  phone: '11999998888',
  status: 'EM_EXECUCAO',
  status_label: 'Em execução',
  can_request_overtime: true,
  overtime: null,
  overtime_options: options,
}

const pendingRequest = {
  id: 9,
  assignment_id: 5,
  minutes: 60,
  minutes_label: '1 h',
  amount_cents: 3000,
  net_cents: 2910,
  status: 'AGUARDANDO_PRESTADOR',
  status_label: 'Aguardando prestador',
  created_at: '2026-11-20T15:00:00Z',
  expires_at: '2026-11-20T15:15:00Z',
  responded_at: null,
}

function candidates(team: object[]) {
  return () => ({
    body: {
      positions: 1,
      filled_positions: 1,
      team_complete: true,
      free_cancel_minutes_before: 1440,
      candidates: [],
      team,
    },
  })
}

function session(team: () => object[]): Record<string, Handler> {
  return {
    'GET /api/auth/me/': () => ({
      body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
    }),
    'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
    'GET /api/vacancies/7/': () => ({ body: vacancy }),
    'GET /api/vacancies/7/candidates/': () => candidates(team())(),
    'GET /api/company/past-workers/?vacancy=7': () => ({ body: { results: [] } }),
    'GET /api/company/assignments/pending/?vacancy=7': () => ({
      body: { results: [], contested: [], arrival_justifications: [] },
    }),
  }
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

describe('Pedir hora extra (US52)', () => {
  it('envia a duração e o valor e mostra o pedido aguardando o prestador', async () => {
    let sent = false
    const calls = mockApi({
      ...session(() => [sent ? { ...member, can_request_overtime: false, overtime: pendingRequest } : member]),
      'POST /api/assignments/5/overtime/': () => {
        sent = true
        return { status: 201, body: pendingRequest }
      },
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Pedir hora extra para Maria' }))
    expect(screen.getByLabelText('Valor da extensão (R$)')).toHaveValue('12,50')
    await userEvent.selectOptions(screen.getByLabelText('Quanto tempo a mais'), '60')
    expect(screen.getByLabelText('Valor da extensão (R$)')).toHaveValue('25,00')
    await userEvent.clear(screen.getByLabelText('Valor da extensão (R$)'))
    await userEvent.type(screen.getByLabelText('Valor da extensão (R$)'), '30,00')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar pedido' }))

    expect(await screen.findByText('Pedido de hora extra enviado. Maria foi avisado.')).toBeInTheDocument()
    expect(screen.getByText(/Hora extra pedida: 1 h por R\$\s?30,00\. Aguardando Maria até/)).toBeInTheDocument()
    const post = calls.find((c) => c.key === 'POST /api/assignments/5/overtime/')
    expect(JSON.parse(post?.body ?? '{}')).toEqual({ minutes: 60, amount_cents: 3000 })
    expect(screen.queryByRole('button', { name: 'Pedir hora extra para Maria' })).not.toBeInTheDocument()
  })

  it('não deixa enviar abaixo do mínimo proporcional', async () => {
    const calls = mockApi(session(() => [member]))
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Pedir hora extra para Maria' }))
    await userEvent.clear(screen.getByLabelText('Valor da extensão (R$)'))
    await userEvent.type(screen.getByLabelText('Valor da extensão (R$)'), '10,00')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar pedido' }))

    expect(screen.getByRole('alert')).toHaveTextContent(/O valor mínimo para 30 min é R\$\s?12,50\./)
    expect(calls.some((c) => c.key.startsWith('POST'))).toBe(false)
  })

  it('mostra quando o pedido expirou e não oferece o botão para quem não está em execução', async () => {
    mockApi(
      session(() => [
        { ...member, overtime: { ...pendingRequest, status: 'EXPIRADO', status_label: 'Expirado' } },
        { id: 6, first_name: 'Ana', phone: '', status: 'CONFIRMADA', status_label: 'Confirmada' },
      ]),
    )
    renderPage()

    expect(
      await screen.findByText('Pedido de hora extra expirou sem resposta. Nada foi cobrado.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pedir hora extra para Maria' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pedir hora extra para Ana' })).not.toBeInTheDocument()
  })
})
