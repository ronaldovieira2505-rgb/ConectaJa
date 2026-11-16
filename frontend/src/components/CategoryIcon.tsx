import {
  Camera,
  HardHat,
  PartyPopper,
  ShoppingBasket,
  Sparkles,
  Truck,
  Wrench,
  type LucideIcon,
  type LucideProps,
} from 'lucide-react'
import { createElement } from 'react'

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  AJUDANTE_OBRA: HardHat,
  CARGA_DESCARGA: Truck,
  VAREJO: ShoppingBasket,
  EVENTOS: PartyPopper,
  FOTOGRAFIA: Camera,
  LIMPEZA: Sparkles,
}

/** Ícone da categoria; as que não têm um próprio usam a ferramenta. */
export default function CategoryIcon({ category, ...props }: LucideProps & { category: string }) {
  return createElement(CATEGORY_ICONS[category] ?? Wrench, { 'aria-hidden': true, ...props })
}
