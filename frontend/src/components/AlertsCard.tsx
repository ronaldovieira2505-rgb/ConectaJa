import { useState } from 'react'
import { api, ApiError, type WorkerProfile } from '../api'
import { Alert, Button, Card, SelectField } from './ui'

const RADII = [5, 10, 20, 50]

/**
 * "Alertas de vagas" (US19): "Nova vaga perto de você" no sino quando uma vaga é publicada a até
 * o raio escolhido da sua casa, nas categorias de Habilidades (sem nenhuma, todas).
 */
export default function AlertsCard({
  profile,
  onSaved,
}: {
  profile: WorkerProfile
  onSaved: (updated: WorkerProfile) => void
}) {
  const current = profile.alerts ?? {
    enabled: false,
    radius_km: 10,
    only_my_schedule: false,
    has_home_location: false,
  }
  const hasSchedule = Boolean(profile.availability?.summary)
  const [enabled, setEnabled] = useState(current.enabled)
  const [radius, setRadius] = useState(current.radius_km)
  const [onlySchedule, setOnlySchedule] = useState(current.only_my_schedule)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [locating, setLocating] = useState(false)

  async function patch(body: Record<string, unknown>, done: string) {
    setError('')
    setNotice('')
    setBusy(true)
    try {
      onSaved(await api<WorkerProfile>('/api/workers/me/', { method: 'PATCH', body }))
      setNotice(done)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível salvar.')
    } finally {
      setBusy(false)
    }
  }

  function useLocation() {
    if (!navigator.geolocation) {
      setError('Seu navegador não oferece localização.')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        await patch(
          {
            home_latitude: pos.coords.latitude.toFixed(6),
            home_longitude: pos.coords.longitude.toFixed(6),
          },
          'Localização de casa salva.',
        )
        setLocating(false)
      },
      () => {
        setError('Não foi possível obter sua localização. Ative a localização e tente de novo.')
        setLocating(false)
      },
    )
  }

  return (
    <Card>
      <h2>Alertas de vagas</h2>
      <p className="sub">
        Receba "Nova vaga perto de você" no sino, no máximo 5 por dia. Usamos as categorias de
        Habilidades; sem nenhuma marcada, valem todas.
      </p>
      <p>
        {current.has_home_location
          ? 'Localização de casa definida.'
          : 'Defina a sua localização de casa para receber alertas.'}{' '}
        <Button variant="secondary" busy={locating} onClick={useLocation}>
          Usar minha localização atual
        </Button>
      </p>
      <label>
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />{' '}
        Receber alertas de vagas perto de mim
      </label>
      <SelectField
        label="Raio"
        value={String(radius)}
        onChange={(e) => setRadius(Number(e.target.value))}
      >
        {RADII.map((km) => (
          <option key={km} value={km}>
            Até {km} km
          </option>
        ))}
      </SelectField>
      {hasSchedule && (
        <label>
          <input
            type="checkbox"
            checked={onlySchedule}
            onChange={(e) => setOnlySchedule(e.target.checked)}
          />{' '}
          Só vagas nos meus horários
        </label>
      )}
      {error && <Alert tone="error">{error}</Alert>}
      {notice && <Alert tone="success">{notice}</Alert>}
      <div className="acoes">
        <Button
          busy={busy && !locating}
          onClick={() =>
            patch(
              { alerts_enabled: enabled, alert_radius_km: radius, alert_only_my_schedule: onlySchedule },
              'Alertas salvos.',
            )
          }
        >
          Salvar alertas
        </Button>
      </div>
    </Card>
  )
}
