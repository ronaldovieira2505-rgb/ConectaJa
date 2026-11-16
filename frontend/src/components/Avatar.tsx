import { Building2 } from 'lucide-react'
import { useState } from 'react'

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ''
  return (parts[0][0] + last).toUpperCase()
}

/**
 * Imagem de quem é o perfil: foto da pessoa (círculo) ou logo da empresa (quadrado).
 * Sem imagem, ou se ela não carregar, mostra as iniciais ou o ícone de empresa.
 */
export default function Avatar({
  src,
  name,
  kind = 'person',
  className = 'size-24',
}: {
  src: string | null | undefined
  name: string
  kind?: 'person' | 'company'
  className?: string
}) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  const shape = kind === 'person' ? 'rounded-full' : 'rounded-[24px]'
  const base = `grid shrink-0 place-items-center overflow-hidden bg-controle ${shape} ${className}`

  if (src && failedSrc !== src) {
    return (
      <span className={base}>
        <img
          src={src}
          alt={kind === 'person' ? `Foto de ${name}` : `Logo de ${name}`}
          className="size-full object-cover"
          onError={() => setFailedSrc(src)}
        />
      </span>
    )
  }
  return (
    <span className={base} aria-hidden="true">
      {kind === 'person' ? (
        <span className="text-[28px] leading-none text-tinta-media">{initials(name)}</span>
      ) : (
        <Building2 className="size-2/5 text-tinta-media" strokeWidth={1} />
      )}
    </span>
  )
}
