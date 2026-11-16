import { ArrowRight, Building2, HardHat } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type VacancyCard } from '../api'
import CategoryGrid from '../components/landing/CategoryGrid'
import Disclosure, { type DisclosureItem } from '../components/landing/Disclosure'
import HomeSearch from '../components/landing/HomeSearch'
import OpenVacancies from '../components/landing/OpenVacancies'

const STEPS = [
  { title: 'A empresa publica e paga', body: 'O valor fica retido antes de a vaga aparecer.' },
  { title: 'O prestador se candidata', body: 'A empresa escolhe quem aprovar.' },
  { title: 'Presença confirmada, PIX feito', body: 'Check-in e check-out por localização.' },
]

const SIDES = [
  {
    icon: HardHat,
    title: 'Quero trabalhar',
    body: 'Veja quanto recebe antes de se candidatar.',
    action: 'Criar conta de prestador',
    to: '/cadastro/prestador',
  },
  {
    icon: Building2,
    title: 'Quero contratar',
    body: 'Publique um turno e escolha entre candidatos verificados.',
    action: 'Cadastrar minha empresa',
    to: '/cadastro/empresa',
  },
]

const QUESTIONS: DisclosureItem[] = [
  {
    title: 'Quanto custa para a empresa?',
    body: (
      <p>
        O valor anunciado, sem mensalidade. A taxa da plataforma sai do repasse ao prestador e
        aparece em cada vaga.
      </p>
    ),
  },
  {
    title: 'Quando o prestador recebe?',
    body: (
      <p>
        Depois do check-out, quando a empresa confirma as horas. Sem resposta no prazo, a aprovação
        é automática.
      </p>
    ),
  },
  {
    title: 'E se alguém faltar ou cancelar?',
    body: (
      <p>
        A posição volta para a busca como urgente. Os prazos e penalidades aparecem na vaga antes
        da candidatura.
      </p>
    ),
  },
  {
    title: 'O pagamento já é real?',
    body: (
      <p>
        Ainda não. Nesta versão o pagamento é simulado: o fluxo é o mesmo, mas nenhum valor é
        cobrado.
      </p>
    ),
  },
]

const SECTION_TITLE = 'mb-5 text-[22px] leading-7'

/** Página inicial pública: busca, categorias e vitrine de vagas, como numa loja. */
export default function LandingPage() {
  const [vacancies, setVacancies] = useState<VacancyCard[]>([])

  useEffect(() => {
    let active = true
    api<{ results: VacancyCard[] }>('/api/vacancies/')
      .then((data) => active && setVacancies(data.results))
      .catch(() => undefined) // sem vitrine, a página continua útil pela busca e pelas categorias
    return () => {
      active = false
    }
  }, [])

  return (
    <div className="flex flex-col gap-12 md:gap-16">
      <HomeSearch />
      <CategoryGrid vacancies={vacancies} />
      <OpenVacancies vacancies={vacancies} />

      <section id="como-funciona" aria-labelledby="como-funciona-titulo">
        <h2 id="como-funciona-titulo" className={SECTION_TITLE}>
          Como funciona
        </h2>
        <ol className="m-0 grid list-none grid-cols-1 gap-3 p-0 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="flex items-start gap-4 rounded-[24px] bg-ficha p-5">
              <span
                className="grid size-8 shrink-0 place-items-center rounded-full bg-tinta text-[13px] text-papel"
                aria-hidden="true"
              >
                {index + 1}
              </span>
              <span className="flex flex-col gap-1">
                <span className="text-[15px] leading-6">{step.title}</span>
                <span className="text-[13px] leading-5 text-tinta-media">{step.body}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="comece-titulo">
        <h2 id="comece-titulo" className={SECTION_TITLE}>
          Comece agora
        </h2>
        <ul className="m-0 grid list-none grid-cols-1 gap-4 p-0 md:grid-cols-2">
          {SIDES.map(({ icon: Icon, title, body, action, to }) => (
            <li
              key={to}
              className="flex flex-col items-start gap-4 rounded-cartao border border-regua bg-papel p-6 md:p-8"
            >
              <Icon className="size-7" strokeWidth={1.25} aria-hidden="true" />
              <div className="flex flex-col gap-1">
                <h3 className="m-0 text-[17px] leading-6 tracking-normal">{title}</h3>
                <p className="m-0 text-[13px] leading-5 text-tinta-media">{body}</p>
              </div>
              <Link to={to} className="btn btn-primary group mt-auto gap-3">
                {action}
                <ArrowRight
                  className="size-4 transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
                  strokeWidth={1.25}
                  aria-hidden="true"
                />
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section id="perguntas" aria-labelledby="perguntas-titulo" className="mx-auto w-full max-w-[800px]">
        <h2 id="perguntas-titulo" className={SECTION_TITLE}>
          Perguntas frequentes
        </h2>
        <Disclosure name="perguntas" items={QUESTIONS} size="large" />
      </section>
    </div>
  )
}
