import { useId } from 'react'
import {
  EQUIPMENT_ITEMS,
  EQUIPMENT_NOTES_MAX,
  type EquipmentEntry,
  type EquipmentProvider,
} from '../equipment'

/** "O que levar e o que é fornecido" (US22): cada item da lista fixa e as observações. */
export default function EquipmentFields({
  value,
  notes,
  onChange,
  onNotesChange,
}: {
  value: EquipmentEntry[]
  notes: string
  onChange: (value: EquipmentEntry[]) => void
  onNotesChange: (notes: string) => void
}) {
  const id = useId()
  const providerOf = (item: string) => value.find((entry) => entry.item === item)?.provider ?? ''

  function choose(item: string, provider: string) {
    const rest = value.filter((entry) => entry.item !== item)
    onChange(provider ? [...rest, { item, provider: provider as EquipmentProvider }] : rest)
  }

  return (
    <fieldset className="bloco">
      <legend>O que levar e o que é fornecido</legend>
      <div className="grade grade-2">
        {EQUIPMENT_ITEMS.map((item) => (
          <div className="field" key={item.value}>
            <label htmlFor={`${id}-${item.value}`}>{item.label}</label>
            <select
              id={`${id}-${item.value}`}
              value={providerOf(item.value)}
              onChange={(e) => choose(item.value, e.target.value)}
            >
              <option value="">Não se aplica</option>
              <option value="PRESTADOR">O prestador leva</option>
              <option value="EMPRESA">A empresa fornece</option>
            </select>
          </div>
        ))}
      </div>
      <div className="field">
        <label htmlFor={`${id}-observacoes`}>Observações</label>
        <textarea
          id={`${id}-observacoes`}
          rows={2}
          maxLength={EQUIPMENT_NOTES_MAX}
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
          placeholder="Ex.: trazer documento com foto para a portaria"
        />
        <small>
          {notes.length}/{EQUIPMENT_NOTES_MAX}
        </small>
      </div>
    </fieldset>
  )
}
