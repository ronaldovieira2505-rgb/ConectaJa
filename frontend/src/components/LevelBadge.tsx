import type { LevelCode } from '../api'
import { Badge } from './ui'

const TONES: Record<LevelCode, 'neutral' | 'warning' | 'info' | 'success'> = {
  NOVO: 'neutral',
  BRONZE: 'warning',
  PRATA: 'info',
  OURO: 'success',
}

/** Selo do nível do prestador (US65): Novo, Bronze, Prata ou Ouro. */
export default function LevelBadge({ code, label }: { code?: LevelCode; label?: string }) {
  if (!code || !label) return null
  return <Badge tone={TONES[code]}>Nível {label}</Badge>
}
