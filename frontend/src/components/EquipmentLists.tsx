/** O que o prestador precisa levar e o que a empresa fornece (US22). Sem nada, não aparece. */
export default function EquipmentLists({
  bring,
  provided,
  notes,
}: {
  bring: string[]
  provided: string[]
  notes: string
}) {
  if (bring.length === 0 && provided.length === 0 && !notes) return null
  return (
    <section aria-labelledby="o-que-levar" className="mt-6 border-t border-regua pt-6">
      <h2 id="o-que-levar">O que levar</h2>
      <div className="grade grade-2">
        {bring.length > 0 && (
          <div>
            <h3 className="m-0 text-[15px] leading-6 tracking-normal">Você precisa levar</h3>
            <ul aria-label="Você precisa levar">
              {bring.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        {provided.length > 0 && (
          <div>
            <h3 className="m-0 text-[15px] leading-6 tracking-normal">Fornecido pela empresa</h3>
            <ul aria-label="Fornecido pela empresa">
              {provided.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {notes && <p className="descricao">{notes}</p>}
    </section>
  )
}
