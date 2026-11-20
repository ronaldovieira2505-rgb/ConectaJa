import { useState } from 'react'
import { api, ApiError, type WorkerProfile } from '../api'
import { Alert, Button, Card } from './ui'

const DAYS = [
  { value: 'SEG', label: 'Segunda' },
  { value: 'TER', label: 'Terça' },
  { value: 'QUA', label: 'Quarta' },
  { value: 'QUI', label: 'Quinta' },
  { value: 'SEX', label: 'Sexta' },
  { value: 'SAB', label: 'Sábado' },
  { value: 'DOM', label: 'Domingo' },
]
const PERIODS = [
  { value: 'MANHA', label: 'Manhã (6h–12h)' },
  { value: 'TARDE', label: 'Tarde (12h–18h)' },
  { value: 'NOITE', label: 'Noite (18h–6h)' },
]

function toggle(list: string[], value: string) {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
}

/** "Disponibilidade" (US10): dias e faixas. Só informativo: não impede candidatura. */
export default function AvailabilityCard({
  profile,
  onSaved,
}: {
  profile: WorkerProfile
  onSaved: (updated: WorkerProfile) => void
}) {
  const current = profile.availability ?? { days: [], periods: [], summary: '' }
  const [editing, setEditing] = useState(false)
  const [days, setDays] = useState<string[]>(current.days)
  const [periods, setPeriods] = useState<string[]>(current.periods)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function save() {
    setError('')
    setSaving(true)
    try {
      onSaved(
        await api<WorkerProfile>('/api/workers/me/', {
          method: 'PATCH',
          body: { availability_days: days, availability_periods: periods },
        }),
      )
      setEditing(false)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível salvar.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <h2>Disponibilidade</h2>
      {editing ? (
        <>
          <fieldset className="m-0 border-0 p-0">
            <legend>Dias</legend>
            <div className="acoes">
              {DAYS.map((day) => (
                <label key={day.value}>
                  <input
                    type="checkbox"
                    checked={days.includes(day.value)}
                    onChange={() => setDays(toggle(days, day.value))}
                  />{' '}
                  {day.label}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className="m-0 border-0 p-0">
            <legend>Horários</legend>
            <div className="acoes">
              {PERIODS.map((period) => (
                <label key={period.value}>
                  <input
                    type="checkbox"
                    checked={periods.includes(period.value)}
                    onChange={() => setPeriods(toggle(periods, period.value))}
                  />{' '}
                  {period.label}
                </label>
              ))}
            </div>
          </fieldset>
          {error && <Alert tone="error">{error}</Alert>}
          <div className="acoes">
            <Button busy={saving} onClick={save}>
              Salvar disponibilidade
            </Button>
            <Button variant="secondary" onClick={() => setEditing(false)}>
              Cancelar
            </Button>
          </div>
        </>
      ) : (
        <>
          <p className={current.summary ? '' : 'sub'}>
            {current.summary ||
              'Informe os dias e horários em que você costuma trabalhar. Você ainda pode se candidatar a qualquer vaga.'}
          </p>
          <div className="acoes">
            <Button
              variant="secondary"
              onClick={() => {
                setDays(current.days)
                setPeriods(current.periods)
                setEditing(true)
              }}
            >
              Editar disponibilidade
            </Button>
          </div>
        </>
      )}
    </Card>
  )
}
