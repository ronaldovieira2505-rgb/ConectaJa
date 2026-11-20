import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import { Alert, Button, Card, Field } from './ui'

/** "Excluir minha conta" (US11): explica o que é apagado e o que fica, e pede a senha. */
export default function DeleteAccountCard() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (!password) {
      setError('Informe a sua senha para confirmar.')
      return
    }
    setBusy(true)
    try {
      await api('/api/workers/me/delete/', { method: 'POST', body: { password } })
      // A página inicial avisa e encerra a sessão local (a do servidor já terminou).
      navigate('/', { replace: true, state: { accountDeleted: true } })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível excluir a conta.')
      setBusy(false)
    }
  }

  return (
    <Card>
      <h2>Excluir minha conta</h2>
      {!open ? (
        <div className="acoes">
          <Button variant="secondary" onClick={() => setOpen(true)}>
            Excluir minha conta
          </Button>
        </div>
      ) : (
        <form onSubmit={submit} noValidate>
          <p>
            <strong>O que é apagado:</strong> nome, CPF, telefone, data de nascimento, e-mail,
            chave PIX, documentos e selfie. Você sai da conta e não consegue mais entrar.
          </p>
          <p>
            <strong>O que é mantido, sem identificar você:</strong> turnos pagos, pagamentos e
            avaliações, por exigência fiscal e de auditoria. Candidaturas pendentes viram
            desistência.
          </p>
          <p>Não é possível desfazer. Com turno em andamento, conclua ou cancele antes.</p>
          <Field
            label="Sua senha"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <Alert tone="error">{error}</Alert>}
          <div className="acoes">
            <Button type="submit" busy={busy}>
              Excluir definitivamente
            </Button>
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Voltar
            </Button>
          </div>
        </form>
      )}
    </Card>
  )
}
