import { render, screen } from '@testing-library/react'
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

const session: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
}

const original = {
  id: 7,
  title: 'Carga e descarga',
  category: 'CARGA_DESCARGA',
  category_label: 'Carga e descarga',
  description: 'Descarregar caminhão',
  street: 'Praça da Sé',
  number: '111',
  complement: 'Loja 2',
  district: 'Sé',
  city: 'São Paulo',
  state: 'SP',
  zip_code: '01001000',
  latitude: '-23.550520',
  longitude: '-46.633308',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  pay_per_person_cents: 12550,
  positions: 3,
  filled_positions: 3,
  total_cents: 37650,
  retained_cents: 0,
  status: 'FINALIZADA',
  status_label: 'Finalizada',
  photo_url: '/api/vacancies/7/photo/?v=abc',
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

describe('Duplicar vaga (US25)', () => {
  it('o detalhe da vaga tem o botão "Duplicar" para o formulário preenchido', async () => {
    mockApi({ ...session, 'GET /api/vacancies/7/': () => ({ body: original }) })

    renderAt('/empresa/vagas/7')

    expect(await screen.findByRole('link', { name: 'Duplicar' })).toHaveAttribute(
      'href',
      '/empresa/vagas/nova?duplicar=7',
    )
  })

  it('a lista "Minhas vagas" também oferece duplicar cada vaga', async () => {
    mockApi({
      ...session,
      'GET /api/company/vacancies/': () => ({
        body: { total_retained_cents: 0, results: [original] },
      }),
    })

    renderAt('/empresa/vagas')

    expect(
      await screen.findByRole('link', { name: 'Duplicar Carga e descarga' }),
    ).toHaveAttribute('href', '/empresa/vagas/nova?duplicar=7')
  })

  it('abre "Nova vaga" com os dados da original e a data e o horário vazios', async () => {
    mockApi({ ...session, 'GET /api/vacancies/7/': () => ({ body: original }) })

    renderAt('/empresa/vagas/nova?duplicar=7')

    expect(await screen.findByLabelText('Título')).toHaveValue('Carga e descarga')
    expect(screen.getByLabelText('Descrição do escopo')).toHaveValue('Descarregar caminhão')
    expect(screen.getByLabelText('Endereço')).toHaveValue('Praça da Sé')
    expect(screen.getByLabelText('Latitude (opcional)')).toHaveValue('-23.550520')
    expect(screen.getByLabelText('Valor por pessoa (R$)')).toHaveValue('125,50')
    expect(screen.getByLabelText('Número de pessoas')).toHaveValue(3)
    expect(screen.getByLabelText('Início')).toHaveValue('')
    expect(screen.getByLabelText('Fim')).toHaveValue('')
    expect(screen.getByText(/Copiamos os dados de “Carga e descarga”/)).toHaveTextContent(
      'A foto da vaga original também será copiada.',
    )
  })

  it('exige a nova data antes de criar e não envia nada sem ela', async () => {
    const fetchMock = mockApi({ ...session, 'GET /api/vacancies/7/': () => ({ body: original }) })
    renderAt('/empresa/vagas/nova?duplicar=7')

    await userEvent.click(await screen.findByRole('button', { name: 'Criar vaga' }))

    expect(screen.getByText('Informe a data e o horário do novo turno.')).toBeInTheDocument()
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')
    expect(posts).toHaveLength(0)
  })

  it('cria a vaga nova com os dados da original e pede a cópia da foto', async () => {
    let sent: Record<string, unknown> = {}
    const created = { ...original, id: 8, status: 'AGUARDANDO_PAGAMENTO', status_label: 'Aguardando pagamento', filled_positions: 0 }
    mockApi({
      ...session,
      'GET /api/vacancies/7/': () => ({ body: original }),
      'POST /api/vacancies/': (init) => {
        sent = JSON.parse(String(init?.body))
        return { status: 201, body: created }
      },
      'GET /api/vacancies/8/': () => ({ body: created }),
    })
    renderAt('/empresa/vagas/nova?duplicar=7')

    await userEvent.type(await screen.findByLabelText('Início'), '2026-12-10T09:00')
    await userEvent.type(screen.getByLabelText('Fim'), '2026-12-10T13:00')
    await userEvent.click(screen.getByRole('button', { name: 'Criar vaga' }))

    expect(await screen.findByRole('button', { name: 'Pagar e publicar' })).toBeInTheDocument()
    expect(sent).toMatchObject({
      duplicate_of: 7,
      title: 'Carga e descarga',
      number: '111',
      complement: 'Loja 2',
      district: 'Sé',
      zip_code: '01001000',
      pay_per_person_cents: 12550,
      positions: 3,
    })
  })

  it('avisa quando a vaga original não pode ser carregada', async () => {
    mockApi({
      ...session,
      'GET /api/vacancies/7/': () => ({ status: 404, body: { detail: 'Vaga não encontrada.' } }),
    })

    renderAt('/empresa/vagas/nova?duplicar=7')

    expect(
      await screen.findByText('Não foi possível carregar a vaga para duplicar.'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Título')).toHaveValue('')
  })
})
