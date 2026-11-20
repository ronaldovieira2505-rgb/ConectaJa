import { useState, type FormEvent } from 'react'
import { api, ApiError, type WorkerProfile } from '../api'
import { CATEGORIES } from '../categories'
import { Alert, Badge, Button, Card } from './ui'

const MAX_SKILLS = 7
const BIO_MAX = 500

/**
 * "Habilidades e experiência" (US08): até 7 categorias das vagas e um resumo de até 500
 * caracteres, sem e-mail nem telefone (o servidor confere).
 */
export default function SkillsCard({
  profile,
  onSaved,
}: {
  profile: WorkerProfile
  onSaved: (updated: WorkerProfile) => void
}) {
  const current = (profile.skills ?? []).map((skill) => skill.value)
  const [editing, setEditing] = useState(false)
  const [skills, setSkills] = useState<string[]>(current)
  const [bio, setBio] = useState(profile.bio ?? '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  function startEditing() {
    setSkills(current)
    setBio(profile.bio ?? '')
    setError('')
    setEditing(true)
  }

  function toggle(value: string) {
    setSkills((list) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]))
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSaving(true)
    try {
      onSaved(
        await api<WorkerProfile>('/api/workers/me/', { method: 'PATCH', body: { skills, bio } }),
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
      <h2 id="habilidades">Habilidades e experiência</h2>
      {editing ? (
        <form onSubmit={save} noValidate>
          <fieldset className="m-0 border-0 p-0">
            <legend>Categorias em que você tem experiência (até {MAX_SKILLS})</legend>
            <div className="acoes">
              {CATEGORIES.map((category) => (
                <label key={category.value}>
                  <input
                    type="checkbox"
                    checked={skills.includes(category.value)}
                    disabled={!skills.includes(category.value) && skills.length >= MAX_SKILLS}
                    onChange={() => toggle(category.value)}
                  />{' '}
                  {category.label}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="field">
            <label htmlFor="resumo-experiencia">Resumo da sua experiência</label>
            <textarea
              id="resumo-experiencia"
              rows={4}
              maxLength={BIO_MAX}
              value={bio}
              onChange={(e) => setBio(e.target.value)}
            />
            <small>
              {bio.length}/{BIO_MAX} · Não coloque e-mail nem telefone: o contato só é liberado
              depois da aprovação.
            </small>
          </div>
          {error && <Alert tone="error">{error}</Alert>}
          <div className="acoes">
            <Button type="submit" busy={saving}>
              Salvar
            </Button>
            <Button type="button" variant="secondary" onClick={() => setEditing(false)}>
              Cancelar
            </Button>
          </div>
        </form>
      ) : (
        <>
          {(profile.skills ?? []).length > 0 && (
            <p className="marcadores">
              {(profile.skills ?? []).map((skill) => (
                <Badge key={skill.value}>{skill.label}</Badge>
              ))}
            </p>
          )}
          <p className={profile.bio ? 'descricao' : 'sub'}>
            {profile.bio ||
              'Conte às empresas em que tipo de serviço você tem experiência. É opcional.'}
          </p>
          <div className="acoes">
            <Button variant="secondary" onClick={startEditing}>
              Editar
            </Button>
          </div>
        </>
      )}
    </Card>
  )
}
