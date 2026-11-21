import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

const detail = {
  id: 7,
  title: 'Carga e descarga',
  company_name: 'Mercado Bom',
  category: 'CARGA_DESCARGA',
  category_label: 'Carga e descarga',
  description: 'Descarregar caminhão',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  district: 'Sé',
  city: 'São Paulo',
  state: 'SP',
  street: 'Praça da Sé',
  number: '1',
  complement: '',
  zip_code: '',
  latitude: '-23.550520',
  longitude: '-46.633308',
  gross_cents: 10000,
  fee_percent: 3,
  fee_cents: 300,
  net_cents: 9700,
  remaining_positions: 1,
  payment_guaranteed: true,
  urgent: false,
  distance_km: null,
  photo_url: null,
  can_apply: false,
  apply_blocker: 'Esta vaga foi finalizada.',
  my_application: { id: 3, status: 'APROVADA', status_label: 'Aprovada' },
  closed: true,
}

function mockApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string) => {
      if (path === '/api/auth/me/') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({ id: 1, name: 'Ana', email: 'a@x.com', role: 'WORKER', verification_status: 'APROVADO' }),
        })
      }
      if (path === '/api/notifications/') {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ unread_count: 0, results: [] }) })
      }
      if (path === '/api/vacancies/7/') {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(detail) })
      }
      throw new Error(`Chamada inesperada: ${path}`)
    }),
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('Vaga encerrada vista por quem participou', () => {
  it('abre o detalhe com o aviso e sem "Em aberto"', async () => {
    mockApi()
    render(
      <MemoryRouter initialEntries={['/vagas/7']}>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { level: 1, name: 'Carga e descarga' })).toBeInTheDocument()
    expect(screen.getByText('Esta vaga foi finalizada.')).toBeInTheDocument()
    expect(screen.queryByText('Em aberto')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Quero esta vaga|Candidatura enviada/ })).not.toBeInTheDocument()
    expect(screen.queryByText('Vaga não encontrada')).not.toBeInTheDocument()
  })
})
