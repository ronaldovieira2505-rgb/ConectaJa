import { useId, useState, type MouseEvent } from 'react'

export const PREMIUM_EXPLANATION =
  'Empresa com histórico de turnos pagos, boas avaliações dos prestadores e nenhuma contestação perdida nem denúncia procedente nos últimos 90 dias.'

/**
 * Selo "Contratante premium" (US66). A explicação curta aparece ao passar o mouse (title) e
 * ao tocar (abre e fecha), para funcionar também no celular.
 */
export default function PremiumBadge({ className = '' }: { className?: string }) {
  const [open, setOpen] = useState(false)
  const id = useId()

  function toggle(event: MouseEvent) {
    // Dentro de um card clicável, o toque no selo não deve abrir a vaga.
    event.preventDefault()
    event.stopPropagation()
    setOpen(!open)
  }

  return (
    <span className={`relative z-10 inline-flex flex-col items-start ${className}`}>
      <button
        type="button"
        title={PREMIUM_EXPLANATION}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={toggle}
        className="badge badge-success cursor-pointer border-0"
      >
        ★ Contratante premium
      </button>
      {open && (
        <span id={id} role="note" className="mt-1 max-w-[18rem] text-[12px] leading-4 text-tinta-media">
          {PREMIUM_EXPLANATION}
        </span>
      )}
    </span>
  )
}
