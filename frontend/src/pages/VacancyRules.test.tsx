import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { formatMinutes } from '../api'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

const rules = {
  free_cancel_minutes_before: 1440,
  late_cancel_block_days: 7,
  geofence_radius_m: 150,
  checkin_open_minutes_before: 30,
  no_show_tolerance_minutes: 30,
  no_show_limit: 2,
  no_show_window_days: 30,
  suspension_days: 15,
  contest_window_minutes: 1440,
}

const vacancy = {
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
  description: 'Descarregar caminhão',
  street: 'Praça da Sé',
  number: '1',
  complement: '',
  zip_code: '',
  latitude: '-23.550520',
  longitude: '-46.633308',
  can_apply: false,
  apply_blocker: 'Entre como prestador para se candidatar.',
  my_application: null,
}

function mockAnonymous(vacancyRules: Record<string, number>) {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string) => {
      const status = path === '/api/auth/me/' ? 403 : 200
      const body = path === '/api/vacancies/7/' ? { ...vacancy, rules: vacancyRules } : {}
      return Promise.resolve({ ok: status === 200, status, json: () => Promise.resolve(body) })
    }),
  )
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={['/vagas/7']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('Regras desta vaga (US16)', () => {
  it('mostra as regras com os valores da plataforma, mesmo para quem não está logado', async () => {
    mockAnonymous(rules)
    renderDetail()

    expect(await screen.findByRole('heading', { name: 'Regras desta vaga' })).toBeInTheDocument()
    expect(
      screen.getByText(
        /Cancelamento sem penalidade até 24 h antes do início; depois disso, 7 dias sem poder se candidatar\./,
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        /Check-in pelo celular a até 150 m do local, a partir de 30 min antes do início; sem check-in até 30 min após o início conta como falta\./,
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/2 faltas em 30 dias suspendem a conta por 15 dias\./),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        /Pagamento garantido: o valor já está em custódia\. Você recebe R\$\s97,00 \(valor do turno menos 3%\) após a confirmação das horas, ou automaticamente 24 h depois do check-out se a empresa não responder\./,
      ),
    ).toBeInTheDocument()
  })

  it('mostra o valor novo quando o admin altera um parâmetro', async () => {
    mockAnonymous({ ...rules, free_cancel_minutes_before: 720, geofence_radius_m: 200 })
    renderDetail()

    expect(await screen.findByText(/Cancelamento sem penalidade até 12 h antes/)).toBeInTheDocument()
    expect(screen.getByText(/a até 200 m do local/)).toBeInTheDocument()
  })

  it('formata prazos de forma amigável', () => {
    expect(formatMinutes(30)).toBe('30 min')
    expect(formatMinutes(1440)).toBe('24 h')
    expect(formatMinutes(2880)).toBe('2 dias')
    expect(formatMinutes(90)).toBe('1 h 30 min')
  })
})
