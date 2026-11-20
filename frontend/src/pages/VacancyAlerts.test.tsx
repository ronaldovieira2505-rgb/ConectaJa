import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

type Handler = (init?: RequestInit) => { status?: number; body?: unknown }

function mockApi(handlers: Record<string, Handler>) {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${path}`
      const handler = handlers[key]
      if (!handler) throw new Error(`Chamada inesperada: ${key}`)
      const { status = 200, body } = handler(init)
      return Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) })
    }),
  )
}

afterEach(() => vi.unstubAllGlobals())

const profile = {
  id: 1,
  full_name: 'Ana Paula Ribeiro',
  cpf: '***.456.789-**',
  phone: '****8888',
  verification_status: 'APROVADO',
  profile_steps: [],
  documents: [],
  availability: { days: ['SEG'], periods: ['MANHA'], summary: 'Seg · manhã' },
  alerts: { enabled: false, radius_km: 10, only_my_schedule: false, has_home_location: false },
}

function setup(patch: Handler) {
  mockApi({
    'GET /api/auth/me/': () => ({
      body: { id: 1, name: 'Ana', email: 'ana@example.com', role: 'WORKER', verification_status: 'APROVADO' },
    }),
    'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
    'GET /api/workers/me/': () => ({ body: profile }),
    'GET /api/workers/me/jobs/': () => ({
      body: { groups: { waiting: [], upcoming: [], in_progress: [], completed: [], closed: [] } },
    }),
    'PATCH /api/workers/me/': patch,
  })
  render(
    <MemoryRouter initialEntries={['/prestador/perfil']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Alertas de vagas (US19)', () => {
  it('salva localização de casa e depois liga os alertas com raio e horários', async () => {
    const sent: unknown[] = []
    vi.stubGlobal('navigator', {
      ...navigator,
      geolocation: {
        getCurrentPosition: (ok: (p: unknown) => void) =>
          ok({ coords: { latitude: -23.54, longitude: -46.63 } }),
      },
    })
    setup((init) => {
      sent.push(JSON.parse(String(init?.body)))
      return { body: { ...profile, alerts: { ...profile.alerts, has_home_location: true } } }
    })
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Usar minha localização atual' }))
    expect(await screen.findByText('Localização de casa salva.')).toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: 'Receber alertas de vagas perto de mim' }))
    await user.selectOptions(screen.getByLabelText('Raio'), 'Até 20 km')
    await user.click(screen.getByRole('checkbox', { name: 'Só vagas nos meus horários' }))
    await user.click(screen.getByRole('button', { name: 'Salvar alertas' }))

    expect(await screen.findByText('Alertas salvos.')).toBeInTheDocument()
    expect(sent).toEqual([
      { home_latitude: '-23.540000', home_longitude: '-46.630000' },
      { alerts_enabled: true, alert_radius_km: 20, alert_only_my_schedule: true },
    ])
  })

  it('mostra o erro quando falta a localização de casa', async () => {
    setup(() => ({
      status: 400,
      body: { detail: 'Defina a sua localização de casa para receber alertas.' },
    }))
    const user = userEvent.setup()

    await user.click(await screen.findByRole('checkbox', { name: 'Receber alertas de vagas perto de mim' }))
    await user.click(screen.getByRole('button', { name: 'Salvar alertas' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Defina a sua localização de casa')
  })
})
