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
      return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
      })
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

const photo = (id: number, caption = '') => ({
  id,
  caption,
  url: `/api/workers/portfolio/${id}/file/`,
})

function session(portfolio: unknown[]): Record<string, Handler> {
  return {
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
        profile_steps: [],
        documents: [],
        portfolio,
      },
    }),
    'GET /api/workers/me/jobs/': () => ({
      body: { groups: { waiting: [], upcoming: [], in_progress: [], completed: [], closed: [] } },
    }),
  }
}

function renderProfile() {
  render(
    <MemoryRouter initialEntries={['/prestador/perfil']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Trabalhos anteriores (US09)', () => {
  it('envia uma foto com legenda e mostra no perfil', async () => {
    let sent: FormData | undefined
    mockApi({
      ...session([]),
      'POST /api/workers/me/portfolio/': (init) => {
        sent = init?.body as FormData
        return { status: 201, body: { results: [photo(5, 'Pintura de fachada')] } }
      },
    })
    renderProfile()
    const user = userEvent.setup()

    await user.upload(
      await screen.findByLabelText('Adicionar foto'),
      new File([new Uint8Array([137, 80, 78, 71])], 'obra.png', { type: 'image/png' }),
    )
    await user.type(screen.getByLabelText('Legenda (opcional)'), 'Pintura de fachada')
    await user.click(screen.getByRole('button', { name: 'Enviar foto' }))

    expect(await screen.findByAltText('Pintura de fachada')).toHaveAttribute(
      'src',
      '/api/workers/portfolio/5/file/',
    )
    expect(sent?.get('caption')).toBe('Pintura de fachada')
    expect((sent?.get('photo') as File).name).toBe('obra.png')
  })

  it('remove a foto depois de confirmar', async () => {
    let removed = false
    mockApi({
      ...session([photo(5, 'Pintura de fachada')]),
      'DELETE /api/workers/me/portfolio/5/': () => {
        removed = true
        return { status: 204 }
      },
    })
    renderProfile()
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Remover Pintura de fachada' }))
    await user.click(screen.getByRole('button', { name: 'Confirmar remoção' }))

    expect(removed).toBe(true)
    expect(screen.queryByAltText('Pintura de fachada')).not.toBeInTheDocument()
  })

  it('com 8 fotos não deixa adicionar outra', async () => {
    mockApi(session(Array.from({ length: 8 }, (_, i) => photo(i + 1, `Foto ${i + 1}`))))

    renderProfile()

    expect(
      await screen.findByText('Você já tem 8 fotos. Remova uma para adicionar outra.'),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('Adicionar foto')).not.toBeInTheDocument()
  })

  it('mostra o erro do servidor', async () => {
    mockApi({
      ...session([]),
      'POST /api/workers/me/portfolio/': () => ({
        status: 400,
        body: { detail: 'Envie a imagem em JPG, PNG ou WebP.' },
      }),
    })
    renderProfile()
    const user = userEvent.setup()

    await user.upload(
      await screen.findByLabelText('Adicionar foto'),
      new File([new Uint8Array([1, 2, 3])], 'obra.png', { type: 'image/png' }),
    )
    await user.click(screen.getByRole('button', { name: 'Enviar foto' }))

    expect(await screen.findByText('Envie a imagem em JPG, PNG ou WebP.')).toBeInTheDocument()
  })
})
