import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api,
  ApiError,
  brl,
  downloadFile,
  formatDateTime,
  formatShift,
  saveFile,
  type Wallet,
} from '../api'
import { Alert, Badge, Button, Card, Loading, SelectField } from '../components/ui'
import {
  STATEMENT_PERIODS,
  statementRange,
  todayInSaoPaulo,
  type StatementPeriod,
} from '../period'

/** Extrato em CSV (US61): o prestador escolhe o período e baixa o arquivo. */
function StatementDownload() {
  const [period, setPeriod] = useState<StatementPeriod>('current_month')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function download() {
    setError('')
    setBusy(true)
    const { from, to } = statementRange(period, todayInSaoPaulo())
    try {
      const file = await downloadFile(
        `/api/workers/me/statement.csv?from=${from}&to=${to}`,
        `extrato-conecta-ja-${to.slice(0, 7)}.csv`,
      )
      saveFile(file.blob, file.filename)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível baixar o extrato.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="carteira-extrato">
      <h2 id="carteira-extrato">Extrato</h2>
      <p className="sub">Turnos pagos no período, em planilha (CSV), com valor, taxa e valor recebido.</p>
      <SelectField
        label="Período"
        value={period}
        onChange={(e) => setPeriod(e.target.value as StatementPeriod)}
      >
        {STATEMENT_PERIODS.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </SelectField>
      <div className="acoes">
        <Button variant="secondary" busy={busy} onClick={download}>
          Baixar extrato
        </Button>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
    </section>
  )
}

/** Carteira do prestador (US60): a receber, liberado e taxas retidas. */
export default function WorkerWalletPage() {
  const [wallet, setWallet] = useState<Wallet | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api<Wallet>('/api/workers/me/wallet/')
      .then(setWallet)
      .catch((err: Error) => setError(err.message))
  }, [])

  if (error) return <Alert tone="error">{error}</Alert>
  if (!wallet) return <Loading />

  const { totals } = wallet

  return (
    <>
      <h1>Carteira</h1>
      <dl className="linhas" aria-label="Totais">
        <div>
          <dt>A receber</dt>
          <dd data-testid="total-receivable">{brl(totals.receivable_cents)}</dd>
        </div>
        <div>
          <dt>Liberado</dt>
          <dd data-testid="total-released">{brl(totals.released_cents)}</dd>
        </div>
        <div>
          <dt>Taxas retidas ({wallet.fee_percent}%)</dt>
          <dd data-testid="total-fees">{brl(totals.fees_cents)}</dd>
        </div>
      </dl>

      <StatementDownload />

      <section aria-labelledby="carteira-a-receber">
        <h2 id="carteira-a-receber">A receber</h2>
        {wallet.receivable.length === 0 && <p>Nenhum valor a receber por enquanto.</p>}
        {wallet.receivable.map((item) => (
          <Card key={item.assignment_id}>
            <h3>
              <Link to={`/vagas/${item.vacancy_id}`}>{item.title}</Link>
            </h3>
            <p className="marcadores">
              <Badge tone="info">{item.status_label}</Badge>
            </p>
            <dl className="linhas">
              <div>
                <dt>Empresa</dt>
                <dd>{item.company_name}</dd>
              </div>
              <div>
                <dt>Turno</dt>
                <dd>{formatShift(item.starts_at, item.ends_at)}</dd>
              </div>
              <div>
                <dt>Valor líquido</dt>
                <dd>{brl(item.net_cents)}</dd>
              </div>
              <div>
                <dt>Previsão de liberação</dt>
                <dd>
                  {item.expected_release_at
                    ? formatDateTime(item.expected_release_at)
                    : item.release_note}
                </dd>
              </div>
            </dl>
          </Card>
        ))}
      </section>

      <section aria-labelledby="carteira-liberado">
        <h2 id="carteira-liberado">Liberado</h2>
        {wallet.released.length === 0 && <p>Nenhum valor liberado ainda.</p>}
        {wallet.released.map((item) => (
          <Card key={item.assignment_id}>
            <h3>
              <Link to={`/vagas/${item.vacancy_id}`}>{item.title}</Link>
            </h3>
            <dl className="linhas">
              <div>
                <dt>Liberado em</dt>
                <dd>{formatDateTime(item.released_at)}</dd>
              </div>
              <div>
                <dt>Valor bruto</dt>
                <dd>{brl(item.gross_cents)}</dd>
              </div>
              <div>
                <dt>Taxa</dt>
                <dd>{brl(item.fee_cents)}</dd>
              </div>
              <div>
                <dt>Valor líquido</dt>
                <dd>{brl(item.net_cents)}</dd>
              </div>
            </dl>
            {item.pix_destination && <p>Enviado para PIX {item.pix_destination} (simulado)</p>}
          </Card>
        ))}
      </section>
    </>
  )
}
