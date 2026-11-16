import { X } from 'lucide-react'
import { useState, type ReactNode } from 'react'

interface HeroProps {
  title: string
  /** Texto curto que aparece no recorte sobre a superfície (abaixo dela no celular). */
  caption: ReactNode
  /** Aviso em vidro sobre a superfície; a pessoa pode dispensar. */
  notice?: string
}

/** Abertura da página inicial: título em gradiente e a superfície da marca com o recorte central. */
export default function Hero({ title, caption, notice }: HeroProps) {
  const [noticeVisible, setNoticeVisible] = useState(true)

  return (
    <section aria-labelledby="hero-titulo">
      <h1
        id="hero-titulo"
        className="gradiente-texto mx-auto mb-14 text-center text-[28px] leading-9 text-balance md:mb-24"
      >
        {title}
      </h1>
      <div className="relative">
        <div className="superficie-gradiente relative aspect-[4/5] min-h-[400px] w-full overflow-hidden rounded-cartao min-[600px]:max-md:aspect-[1.35] md:aspect-[1376/560] md:min-h-0 motion-safe:animate-sobe">
          {notice && noticeVisible && (
            <div className="absolute top-4 left-4 flex items-center gap-3 rounded-full bg-vidro py-2 pr-2 pl-4 text-[13px] leading-4 backdrop-blur-flutuante md:top-auto md:bottom-6 md:left-6">
              <p className="m-0 max-w-[220px]">{notice}</p>
              <button
                type="button"
                className="grid size-8 cursor-pointer place-items-center rounded-full border-0 bg-transparent p-0 text-tinta hover:bg-controle"
                onClick={() => setNoticeVisible(false)}
                aria-label="Dispensar aviso"
              >
                <X className="size-4" strokeWidth={1.5} aria-hidden="true" />
              </button>
            </div>
          )}
        </div>
        <div className="pt-5 text-center text-[13px] leading-[22px] md:absolute md:top-0 md:left-1/2 md:w-max md:max-w-[calc(100%-80px)] md:-translate-x-1/2 md:rounded-b-[40px] md:bg-concreto md:px-12 md:pt-6 md:pb-8 md:text-[15px] md:leading-6 md:before:absolute md:before:top-0 md:before:right-full md:before:size-10 md:before:rounded-tr-[40px] md:before:shadow-[20px_-20px_0_20px_var(--concreto)] md:before:content-[''] md:after:absolute md:after:top-0 md:after:left-full md:after:size-10 md:after:rounded-tl-[40px] md:after:shadow-[-20px_-20px_0_20px_var(--concreto)] md:after:content-['']">
          <p className="m-0 mx-auto max-w-[36ch]">{caption}</p>
        </div>
      </div>
    </section>
  )
}
