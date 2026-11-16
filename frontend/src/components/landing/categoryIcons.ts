import {
  Camera,
  HardHat,
  PartyPopper,
  ShoppingBasket,
  Sparkles,
  Truck,
  Wrench,
  type LucideIcon,
} from 'lucide-react'

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  AJUDANTE_OBRA: HardHat,
  CARGA_DESCARGA: Truck,
  VAREJO: ShoppingBasket,
  EVENTOS: PartyPopper,
  FOTOGRAFIA: Camera,
  LIMPEZA: Sparkles,
}

/** Ícone da categoria; as que não têm um próprio usam a ferramenta. */
export function categoryIcon(category: string): LucideIcon {
  return CATEGORY_ICONS[category] ?? Wrench
}
