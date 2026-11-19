import type { ReactNode } from 'react'

export interface DisclosureItem {
  title: string
  body: ReactNode
}

/**
 * Lista de itens que abrem um de cada vez (o `name` compartilhado fecha os outros).
 * `size="compact"` é a lista curta ao lado de uma seção; `size="large"` é a de perguntas.
 */
export default function Disclosure({
  name,
  items,
  size = 'compact',
}: {
  name: string
  items: DisclosureItem[]
  size?: 'compact' | 'large'
}) {
  const large = size === 'large'
  return (
    <div className="w-full">
      {items.map((item, index) => (
        <details
          key={item.title}
          className={`group border-t border-regua last:border-b ${large ? 'py-1' : 'py-4'}`}
          name={name}
          open={!large && index === 0}
        >
          <summary
            className={`flex cursor-pointer list-none items-center justify-between gap-5 [&::-webkit-details-marker]:hidden ${
              large ? 'min-h-[72px] text-[15px] leading-6' : 'text-[13px] leading-6'
            }`}
          >
            {item.title}
            <span
              className="mx-2 size-1.5 shrink-0 rotate-45 border-t-[1.5px] border-r-[1.5px] border-current transition-transform duration-200 group-open:rotate-135 motion-reduce:transition-none"
              aria-hidden="true"
            />
          </summary>
          <div
            className={`text-tinta-media [&_p]:m-0 ${large ? 'max-w-[700px] pr-8 pb-6' : 'max-w-[344px] pt-2 pr-6'}`}
          >
            {item.body}
          </div>
        </details>
      ))}
    </div>
  )
}
