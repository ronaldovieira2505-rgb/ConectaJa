/**
 * Cor de cada categoria de vaga: dá vida aos ícones, às capas sem foto e aos atalhos da busca.
 * `from` e `to` formam o gradiente; `soft` é o fundo claro; `ink` é o texto sobre o fundo claro.
 */
export interface CategoryColor {
  from: string
  to: string
  soft: string
  ink: string
}

const COLORS: Record<string, CategoryColor> = {
  AJUDANTE_OBRA: { from: '#F59E0B', to: '#EA580C', soft: '#FFF4E0', ink: '#9A4A06' },
  CARGA_DESCARGA: { from: '#3B82F6', to: '#4F46E5', soft: '#E8F0FF', ink: '#2C3FA6' },
  VAREJO: { from: '#10B981', to: '#0D9488', soft: '#E3F7F0', ink: '#0B6B5D' },
  EVENTOS: { from: '#EC4899', to: '#A855F7', soft: '#FCE8F4', ink: '#8E2A6E' },
  FOTOGRAFIA: { from: '#8B5CF6', to: '#6366F1', soft: '#EFEBFF', ink: '#4C3BB0' },
  LIMPEZA: { from: '#06B6D4', to: '#3B82F6', soft: '#E2F6FB', ink: '#0B6A86' },
  OUTROS: { from: '#F43F5E', to: '#F97316', soft: '#FFE9EC', ink: '#A12A3E' },
}

export function categoryColor(category: string): CategoryColor {
  return COLORS[category] ?? COLORS.OUTROS
}

export function categoryGradient(category: string, angle = 135): string {
  const { from, to } = categoryColor(category)
  return `linear-gradient(${angle}deg, ${from}, ${to})`
}
