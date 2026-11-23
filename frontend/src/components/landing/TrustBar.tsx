import { MapPinCheck, ShieldCheck, UserCheck, type LucideIcon } from 'lucide-react'

const ITEMS: { icon: LucideIcon; title: string; body: string; color: string; soft: string }[] = [
  {
    icon: ShieldCheck,
    title: 'Pagamento em custódia',
    body: 'Só aparece na busca a vaga já paga.',
    color: '#0B6B5D',
    soft: '#E3F7F0',
  },
  {
    icon: UserCheck,
    title: 'Cadastros verificados',
    body: 'CNPJ, documento, selfie e PIX do titular.',
    color: '#2C3FA6',
    soft: '#E8F0FF',
  },
  {
    icon: MapPinCheck,
    title: 'Presença por localização',
    body: 'O check-in só vale no endereço do turno.',
    color: '#8E2A6E',
    soft: '#FCE8F4',
  },
]

/** Faixa logo abaixo da busca com as três garantias do produto. */
export default function TrustBar() {
  return (
    <ul
      aria-label="Garantias do Conecta Já"
      className="m-0 grid list-none grid-cols-1 gap-3 p-0 md:grid-cols-3"
    >
      {ITEMS.map(({ icon: Icon, title, body, color, soft }) => (
        <li key={title} className="flex items-center gap-4 rounded-[24px] border border-regua bg-papel p-4">
          <span
            className="grid size-11 shrink-0 place-items-center rounded-2xl"
            style={{ backgroundColor: soft, color }}
            aria-hidden="true"
          >
            <Icon className="size-6" strokeWidth={1.5} />
          </span>
          <span className="flex flex-col">
            <span className="text-[15px] leading-6">{title}</span>
            <span className="text-[13px] leading-5 text-tinta-media">{body}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}
