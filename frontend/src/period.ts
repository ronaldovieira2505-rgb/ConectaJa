/** Períodos prontos do extrato (US61), em datas AAAA-MM-DD no horário de São Paulo. */
export type StatementPeriod = 'current_month' | 'previous_month' | 'last_90_days'

export const STATEMENT_PERIODS: { value: StatementPeriod; label: string }[] = [
  { value: 'current_month', label: 'Mês atual' },
  { value: 'previous_month', label: 'Mês anterior' },
  { value: 'last_90_days', label: 'Últimos 90 dias' },
]

/** Data de hoje em São Paulo, como AAAA-MM-DD. */
export function todayInSaoPaulo(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Sao_Paulo',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now)
}

function iso(year: number, monthIndex: number, day: number): string {
  return new Date(Date.UTC(year, monthIndex, day)).toISOString().slice(0, 10)
}

/** Início e fim (inclusivos) do período escolhido, a partir de `today` (AAAA-MM-DD). */
export function statementRange(period: StatementPeriod, today: string): { from: string; to: string } {
  const [year, month, day] = today.split('-').map(Number)
  if (period === 'previous_month') {
    // Dia 0 do mês atual = último dia do mês anterior.
    return { from: iso(year, month - 2, 1), to: iso(year, month - 1, 0) }
  }
  if (period === 'last_90_days') {
    return { from: iso(year, month - 1, day - 89), to: today }
  }
  return { from: iso(year, month - 1, 1), to: today }
}
