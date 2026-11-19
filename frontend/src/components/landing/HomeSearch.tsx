import { Search } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

/** Abertura da página inicial: a busca de vagas é a primeira ação da tela. */
export default function HomeSearch() {
  const [term, setTerm] = useState('')
  const navigate = useNavigate()

  function submit(event: FormEvent) {
    event.preventDefault()
    const q = term.trim()
    navigate(q ? `/vagas?q=${encodeURIComponent(q)}` : '/vagas')
  }

  return (
    <section
      aria-labelledby="busca-titulo"
      className="superficie-gradiente flex flex-col items-center gap-6 rounded-cartao px-4 py-10 text-center md:gap-8 md:px-12 md:py-16 motion-safe:animate-sobe"
    >
      <h1
        id="busca-titulo"
        className="m-0 text-[28px] leading-9 text-balance md:text-[40px] md:leading-[48px]"
      >
        Que turno você procura?
      </h1>
      <form
        role="search"
        onSubmit={submit}
        className="flex w-full max-w-[640px] items-center gap-2 rounded-full bg-papel py-1.5 pr-1.5 pl-5 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-foco"
      >
        <Search className="size-5 shrink-0 text-tinta-media" strokeWidth={1.5} aria-hidden="true" />
        <input
          type="search"
          aria-label="Buscar vagas"
          placeholder="Ex.: limpeza, carga, eventos"
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          className="h-11 min-w-0 flex-1 border-0 bg-transparent font-texto text-[15px] text-tinta outline-none placeholder:text-tinta-media"
        />
        <button type="submit" className="btn btn-primary">
          Buscar
        </button>
      </form>
      <p className="m-0 max-w-none text-[13px] leading-5">
        Pagamento retido antes do turno.{' '}
        <Link to="/cadastro/empresa">Sou empresa e quero publicar</Link>
      </p>
    </section>
  )
}
