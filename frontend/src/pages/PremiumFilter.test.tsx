import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

const card = {
  id: 7,
  title: 'Carga e descarga',
  company_name: 'Mercado Bom',
  category: 'CARGA_DESCARGA',
  category_label: 'Carga e descarga',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  district: 'Sé',
  city: 'São Paulo',
  state: 'SP',
  gross_cents: 10000,
  fee_percent: 3,
  fee_cents: 300,
  net_cents: 9700,
  remaining_positions: 2,
  payment_guaranteed: true,
  urgent: false,
  distance_km: null,
  photo_url: null,
}

const calls: string[] = []

/** Visitante sem login; com `premium=1` não há vagas premium. */
function mockApi() {
  calls.length = 0
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string) => {
      calls.push(path)
      if (path === '/api/auth/me/') {
        return Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({}) })
      }
      const results = path.includes('premium=1') ? [] : [card]
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ results }) })
    }),
  )
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

afterEach(() => vi.unstubAllGlobals())

describe('Só contratantes premium (US67)', () => {
  it('combina com os outros filtros, mostra o vazio próprio e limpa tudo', async () => {
    mockApi()
    renderAt('/vagas')
    await screen.findByText(/R\$\s97,00/)
    const user = userEvent.setup()

    await user.selectOptions(screen.getByLabelText('Categoria'), 'LIMPEZA')
    await user.click(screen.getByLabelText('Só contratantes premium'))
    expect(screen.getByRole('button', { name: 'Filtros' })).toBeInTheDocument() // ainda não aplicado
    await user.click(screen.getByRole('button', { name: 'Buscar' }))

    expect(
      await screen.findByRole('heading', { name: 'Nenhuma vaga de contratante premium com esses filtros' }),
    ).toBeInTheDocument()
    const last = calls.filter((c) => c.startsWith('/api/vacancies/')).at(-1) ?? ''
    expect(last).toContain('premium=1')
    expect(last).toContain('category=LIMPEZA')
    // No celular, o contador conta o filtro premium (categoria + premium).
    expect(screen.getByRole('button', { name: 'Filtros (2)' })).toBeInTheDocument()

    const clears = screen.getAllByRole('button', { name: 'Limpar filtros' })
    await user.click(clears[clears.length - 1])
    expect(await screen.findByText(/R\$\s97,00/)).toBeInTheDocument()
    expect(screen.getByLabelText('Só contratantes premium')).not.toBeChecked()
    const after = calls.filter((c) => c.startsWith('/api/vacancies/')).at(-1) ?? ''
    expect(after).not.toContain('premium')
  })
})
