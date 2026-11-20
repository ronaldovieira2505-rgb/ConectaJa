/** EPIs, uniforme e ferramentas (US22): a mesma lista fixa do backend, na mesma ordem. */
export const EQUIPMENT_ITEMS = [
  { value: 'CAPACETE', label: 'Capacete' },
  { value: 'LUVAS', label: 'Luvas' },
  { value: 'BOTINA', label: 'Botina' },
  { value: 'OCULOS_PROTECAO', label: 'Óculos de proteção' },
  { value: 'PROTETOR_AURICULAR', label: 'Protetor auricular' },
  { value: 'COLETE_REFLETIVO', label: 'Colete refletivo' },
  { value: 'UNIFORME', label: 'Uniforme' },
  { value: 'CALCA_PRETA', label: 'Calça preta' },
  { value: 'CAMISA_BRANCA', label: 'Camisa branca' },
  { value: 'SAPATO_SOCIAL', label: 'Sapato social' },
  { value: 'FERRAMENTAS_PROPRIAS', label: 'Ferramentas próprias' },
]

export type EquipmentProvider = 'PRESTADOR' | 'EMPRESA'

export interface EquipmentEntry {
  item: string
  provider: EquipmentProvider
}

export const EQUIPMENT_NOTES_MAX = 300

export function equipmentLabel(item: string): string {
  return EQUIPMENT_ITEMS.find((i) => i.value === item)?.label ?? item
}
