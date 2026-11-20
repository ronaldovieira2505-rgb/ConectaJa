import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

type Handler = (init?: RequestInit) => { status?: number; body?: unknown }

function mockApi(handlers: Record<string, Handler>) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${path}`
      calls.push(key)
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

const session: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Ana', email: 'ana@example.com', role: 'WORKER', verification_status: 'APROVADO' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
  'GET /api/workers/me/': () => ({
    body: {
      id: 1,
      full_name: 'Ana Paula Ribeiro',
      cpf: '***.456.789-**',
      phone: '****8888',
      verification_status: 'APROVADO',
      pix_key: '***.456.789-**',
      profile_steps: [],
      documents: [],
    },
  }),
  'GET /api/workers/me/jobs/': () => ({
    body: { groups: { waiting: [], upcoming: [], in_progress: [], completed: [], closed: [] } },
  }),
}

async function openAndConfirm(password: string) {
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Excluir minha conta' }))
  if (password) await user.type(screen.getByLabelText('Sua senha'), password)
  await user.click(screen.getByRole('button', { name: 'Excluir definitivamente' }))
}

describe('Excluir minha conta (US11)', () => {
  it('explica o que é apagado, exclui com a senha e volta para a página inicial deslogado', async () => {
    let sent: unknown
    const calls = mockApi({
      ...session,
      'POST /api/workers/me/delete/': (init) => {
        sent = JSON.parse(String(init?.body))
        return { status: 204 }
      },
      'GET /api/vacancies/': () => ({ body: { results: [] } }),
    })
    renderAt('/prestador/perfil')

    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Excluir minha conta' }))
    expect(screen.getByText(/O que é apagado:/).parentElement).toHaveTextContent('chave PIX, documentos e selfie')
    expect(screen.getByText(/O que é mantido, sem identificar você:/)).toBeInTheDocument()
    await user.type(screen.getByLabelText('Sua senha'), 'senha-forte-123')
    await user.click(screen.getByRole('button', { name: 'Excluir definitivamente' }))

    expect(
      await screen.findByText('Sua conta foi excluída e seus dados pessoais foram apagados.'),
    ).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Entrar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sair' })).not.toBeInTheDocument()
    expect(sent).toEqual({ password: 'senha-forte-123' })
    expect(calls).not.toContain('POST /api/auth/logout/')
  })

  it('senha errada mostra o erro e mantém a conta', async () => {
    mockApi({
      ...session,
      'POST /api/workers/me/delete/': () => ({ status: 403, body: { detail: 'Senha incorreta.' } }),
    })
    renderAt('/prestador/perfil')

    await openAndConfirm('errada')

    expect(await screen.findByText('Senha incorreta.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ana Paula Ribeiro' })).toBeInTheDocument()
  })

  it('com turno em andamento mostra o motivo da recusa', async () => {
    const message = 'Você tem turnos em andamento. Conclua ou cancele antes de excluir a conta.'
    mockApi({
      ...session,
      'POST /api/workers/me/delete/': () => ({ status: 409, body: { detail: message } }),
    })
    renderAt('/prestador/perfil')

    await openAndConfirm('senha-forte-123')

    expect(await screen.findByText(message)).toBeInTheDocument()
  })

  it('pede a senha antes de enviar', async () => {
    const calls = mockApi(session)
    renderAt('/prestador/perfil')

    await openAndConfirm('')

    expect(screen.getByText('Informe a sua senha para confirmar.')).toBeInTheDocument()
    expect(calls).not.toContain('POST /api/workers/me/delete/')
  })
})
