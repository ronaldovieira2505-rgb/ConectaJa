import { describe, expect, it } from 'vitest'
import { statementRange, todayInSaoPaulo } from './period'

describe('Períodos do extrato (US61)', () => {
  it('mês atual vai do dia 1 até hoje', () => {
    expect(statementRange('current_month', '2026-11-20')).toEqual({
      from: '2026-11-01',
      to: '2026-11-20',
    })
  })

  it('mês anterior vai do primeiro ao último dia, inclusive na virada do ano', () => {
    expect(statementRange('previous_month', '2026-11-20')).toEqual({
      from: '2026-10-01',
      to: '2026-10-31',
    })
    expect(statementRange('previous_month', '2026-01-15')).toEqual({
      from: '2025-12-01',
      to: '2025-12-31',
    })
  })

  it('últimos 90 dias contam hoje como um deles', () => {
    expect(statementRange('last_90_days', '2026-11-20')).toEqual({
      from: '2026-08-23',
      to: '2026-11-20',
    })
  })

  it('o dia de hoje segue o horário de São Paulo', () => {
    expect(todayInSaoPaulo(new Date('2026-12-01T01:30:00Z'))).toBe('2026-11-30')
  })
})
