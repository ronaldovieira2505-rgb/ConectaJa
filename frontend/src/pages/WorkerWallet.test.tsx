import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

const STATEMENT = '/api/workers/me/statement.csv'

function mockApi(wallet: unknown, statement?: () => unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string) => {
      if (statement && path.startsWith(`${STATEMENT}?`)) return Promise.resolve(statement())
      const bodies: Record<string, unknown> = {
        '/api/auth/me/': {
          id: 1,
          name: 'João',
          email: 'joao@example.com',
          role: 'WORKER',
          verification_status: 'APROVADO',
        },
        '/api/notifications/': { unread_count: 0, results: [] },
        '/api/workers/me/wallet/': wallet,
      }
      if (!(path in bodies)) throw new Error(`Chamada inesperada: ${path}`)
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(bodies[path]) })
    }),
  )
}

function renderWallet() {
  render(
    <MemoryRouter initialEntries={['/carteira']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

const shift = {
  vacancy_id: 7,
  title: 'Carga e descarga',
  company_name: 'Mercado Bom',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Carteira do prestador (US60)', () => {
  it('mostra os três totais e os itens a receber e liberados', async () => {
    mockApi({
      totals: { receivable_cents: 9700, released_cents: 19400, fees_cents: 600 },
      fee_percent: 3,
      receivable: [
        {
          ...shift,
          assignment_id: 1,
          status: 'CONFIRMADA',
          status_label: 'Confirmada',
          net_cents: 9700,
          expected_release_at: '2026-11-04T16:00:00Z',
          release_note: '',
        },
        {
          ...shift,
          assignment_id: 2,
          title: 'Evento',
          status: 'APROVADA',
          status_label: 'Aprovada',
          net_cents: 9700,
          expected_release_at: null,
          release_note: 'após confirmação da empresa',
        },
      ],
      released: [
        {
          ...shift,
          assignment_id: 3,
          released_at: '2026-11-04T10:30:00Z',
          gross_cents: 10000,
          fee_cents: 300,
          net_cents: 9700,
          pix_destination: 'j***@gmail.com',
        },
      ],
    })

    renderWallet()

    expect(await screen.findByRole('heading', { name: 'Carteira' })).toBeInTheDocument()
    expect(screen.getByTestId('total-receivable')).toHaveTextContent('R$ 97,00')
    expect(screen.getByTestId('total-released')).toHaveTextContent('R$ 194,00')
    expect(screen.getByTestId('total-fees')).toHaveTextContent('R$ 6,00')
    expect(screen.getByText('após confirmação da empresa')).toBeInTheDocument()
    const released = screen.getByRole('region', { name: 'Liberado' })
    expect(within(released).getByText('R$ 100,00')).toBeInTheDocument()
    expect(within(released).getByText('R$ 3,00')).toBeInTheDocument()
    expect(within(released).getByText(/Enviado para PIX j\*\*\*@gmail\.com/)).toBeInTheDocument()
  })

  it('mostra mensagens vazias quando não há valores', async () => {
    mockApi({
      totals: { receivable_cents: 0, released_cents: 0, fees_cents: 0 },
      fee_percent: 3,
      receivable: [],
      released: [],
    })

    renderWallet()

    expect(await screen.findByText('Nenhum valor a receber por enquanto.')).toBeInTheDocument()
    expect(screen.getByText('Nenhum valor liberado ainda.')).toBeInTheDocument()
  })
})

const EMPTY_WALLET = {
  totals: { receivable_cents: 0, released_cents: 0, fees_cents: 0 },
  fee_percent: 3,
  receivable: [],
  released: [],
}

describe('Extrato do prestador (US61)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('baixa o CSV do período escolhido com o nome enviado pelo servidor', async () => {
    mockApi(EMPTY_WALLET, () => ({
      ok: true,
      status: 200,
      headers: new Headers({
        'Content-Disposition': 'attachment; filename="extrato-conecta-ja-2026-10.csv"',
      }),
      blob: () => Promise.resolve(new Blob(['﻿cabeçalho'])),
    }))
    Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:extrato', configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: () => undefined, configurable: true })
    let downloaded = ''
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloaded = this.download
    })
    renderWallet()
    const user = userEvent.setup()

    await user.selectOptions(await screen.findByLabelText('Período'), 'Mês anterior')
    await user.click(screen.getByRole('button', { name: 'Baixar extrato' }))

    const calls = vi.mocked(fetch).mock.calls.map(([path]) => String(path))
    const request = calls.find((path) => path.startsWith(STATEMENT))
    expect(request).toMatch(/\?from=\d{4}-\d{2}-01&to=\d{4}-\d{2}-\d{2}$/)
    expect(downloaded).toBe('extrato-conecta-ja-2026-10.csv')
  })

  it('mostra o erro do servidor quando o período é recusado', async () => {
    mockApi(EMPTY_WALLET, () => ({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'O período pode ter no máximo 366 dias.' }),
    }))
    renderWallet()
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Baixar extrato' }))

    expect(await screen.findByText('O período pode ter no máximo 366 dias.')).toBeInTheDocument()
  })
})
