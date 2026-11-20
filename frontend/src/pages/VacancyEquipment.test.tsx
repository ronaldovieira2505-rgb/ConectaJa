import { render, screen, within } from '@testing-library/react'
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
      return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
      })
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

afterEach(() => {
  vi.unstubAllGlobals()
})

const companySession: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
  'GET /api/vacancies/7/candidates/': () => ({
    body: { positions: 1, filled_positions: 0, team_complete: false, candidates: [], team: [] },
  }),
}

const vacancy = {
  id: 7,
  title: 'Ajudante de obra',
  category: 'AJUDANTE_OBRA',
  category_label: 'Ajudante de obra',
  description: 'Carregar material',
  street: 'Rua A',
  city: 'São Paulo',
  state: 'SP',
  latitude: '-23.550520',
  longitude: '-46.633308',
  starts_at: '2026-11-25T12:00:00Z',
  ends_at: '2026-11-25T16:00:00Z',
  pay_per_person_cents: 10000,
  positions: 1,
  filled_positions: 0,
  total_cents: 10000,
  retained_cents: 10000,
  status: 'PUBLICADA',
  status_label: 'Publicada',
  photo_url: null,
  equipment: [
    { item: 'LUVAS', provider: 'EMPRESA' },
    { item: 'BOTINA', provider: 'PRESTADOR' },
  ],
  equipment_notes: 'Trazer documento com foto.',
}

describe('EPIs, uniforme e ferramentas (US22)', () => {
  it('a empresa marca quem leva cada item ao criar a vaga', async () => {
    let sent: Record<string, unknown> = {}
    mockApi({
      ...companySession,
      'POST /api/vacancies/': (init) => {
        sent = JSON.parse(String(init?.body))
        return { status: 201, body: vacancy }
      },
      'GET /api/vacancies/7/': () => ({ body: vacancy }),
    })
    renderAt('/empresa/vagas/nova')
    const user = userEvent.setup()

    await user.selectOptions(await screen.findByLabelText('Luvas'), 'A empresa fornece')
    await user.selectOptions(screen.getByLabelText('Botina'), 'O prestador leva')
    await user.type(screen.getByLabelText('Observações'), 'Trazer documento com foto.')
    await user.click(screen.getByRole('button', { name: 'Criar vaga' }))

    expect(await screen.findByRole('heading', { name: 'Ajudante de obra' })).toBeInTheDocument()
    expect(sent.equipment).toEqual([
      { item: 'LUVAS', provider: 'EMPRESA' },
      { item: 'BOTINA', provider: 'PRESTADOR' },
    ])
    expect(sent.equipment_notes).toBe('Trazer documento com foto.')
  })

  it('a edição abre com os itens marcados e envia a alteração', async () => {
    let sent: Record<string, unknown> = {}
    mockApi({
      ...companySession,
      'GET /api/vacancies/7/': () => ({ body: vacancy }),
      'PATCH /api/vacancies/7/': (init) => {
        sent = JSON.parse(String(init?.body))
        return { body: vacancy }
      },
    })
    renderAt('/empresa/vagas/7')
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Editar' }))
    expect(screen.getByLabelText('Luvas')).toHaveValue('EMPRESA')
    await user.selectOptions(screen.getByLabelText('Capacete'), 'A empresa fornece')
    await user.click(screen.getByRole('button', { name: 'Salvar alterações' }))

    expect(await screen.findByText('Alterações salvas.')).toBeInTheDocument()
    expect(sent.equipment).toEqual(
      expect.arrayContaining([
        { item: 'LUVAS', provider: 'EMPRESA' },
        { item: 'BOTINA', provider: 'PRESTADOR' },
        { item: 'CAPACETE', provider: 'EMPRESA' },
      ]),
    )
  })

  const detail = {
    id: 7,
    title: 'Ajudante de obra',
    company_name: 'Acme',
    category: 'AJUDANTE_OBRA',
    category_label: 'Ajudante de obra',
    starts_at: '2026-11-25T12:00:00Z',
    ends_at: '2026-11-25T16:00:00Z',
    district: 'Sé',
    city: 'São Paulo',
    state: 'SP',
    gross_cents: 10000,
    fee_percent: 3,
    fee_cents: 300,
    net_cents: 9700,
    remaining_positions: 1,
    payment_guaranteed: true,
    urgent: false,
    distance_km: null,
    photo_url: null,
    description: 'Carregar material',
    street: 'Rua A',
    number: '1',
    complement: '',
    zip_code: '',
    latitude: '-23.550520',
    longitude: '-46.633308',
    can_apply: false,
    apply_blocker: 'Entre como prestador para se candidatar.',
    my_application: null,
  }

  function mockVisitor(equipment: unknown) {
    mockApi({
      'GET /api/auth/me/': () => ({ status: 403, body: {} }),
      'GET /api/vacancies/7/': () => ({ body: { ...detail, equipment } }),
    })
  }

  it('o prestador vê o que precisa levar e o que a empresa fornece, separados', async () => {
    mockVisitor({ bring: ['Botina'], provided: ['Capacete', 'Luvas'], notes: 'Portaria pela Rua B.' })

    renderAt('/vagas/7')

    const block = await screen.findByRole('region', { name: 'O que levar' })
    expect(within(within(block).getByRole('list', { name: 'Você precisa levar' })).getByText('Botina')).toBeInTheDocument()
    const provided = within(block).getByRole('list', { name: 'Fornecido pela empresa' })
    expect(within(provided).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['Capacete', 'Luvas'])
    expect(within(block).getByText('Portaria pela Rua B.')).toBeInTheDocument()
  })

  it('sem itens marcados o bloco não aparece', async () => {
    mockVisitor({ bring: [], provided: [], notes: '' })

    renderAt('/vagas/7')

    expect(await screen.findByRole('heading', { level: 1, name: 'Ajudante de obra' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'O que levar' })).not.toBeInTheDocument()
  })
})
