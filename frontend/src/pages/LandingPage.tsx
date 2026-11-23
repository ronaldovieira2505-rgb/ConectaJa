import { ArrowRight, Banknote, Building2, HardHat, MapPinCheck, Megaphone } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api, type VacancyCard } from '../api'
import { useAuth } from '../authContext'
import { Alert } from '../components/ui'
import CategoryGrid from '../components/landing/CategoryGrid'
import Disclosure, { type DisclosureItem } from '../components/landing/Disclosure'
import HomeSearch from '../components/landing/HomeSearch'
import TrustBar from '../components/landing/TrustBar'
import OpenVacancies from '../components/landing/OpenVacancies'

const STEPS = [
  {
    icon: Megaphone,
    color: '#4A74C9',
    title: 'A empresa publica e paga',
    body: 'O valor fica retido antes de a vaga aparecer.',
  },
  {
    icon: MapPinCheck,
    color: '#8C5DC0',
    title: 'O prestador vai ao turno',
    body: 'A empresa aprova e o check-in é feito no local.',
  },
  {
    icon: Banknote,
    color: '#D9637A',
    title: 'Horas confirmadas, PIX feito',
    body: 'O valor é liberado assim que a presença é confirmada.',
  },
]

const SIDES = [
  {
    icon: HardHat,
    gradient: 'linear-gradient(135deg, #F59E0B, #EA580C)',
    title: 'Quero trabalhar',
    body: 'Veja quanto recebe antes de se candidatar.',
    action: 'Criar conta de prestador',
    to: '/cadastro/prestador',
  },
  {
    icon: Building2,
    gradient: 'linear-gradient(135deg, #4A74C9, #8C5DC0)',
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
  const location = useLocation()
  const { forget } = useAuth()
  // Conta recém-excluída (US11): estado interno da navegação, não dá para digitar na URL.
  const accountDeleted = Boolean(
    (location.state as { accountDeleted?: boolean } | null)?.accountDeleted,
  )
  const [vacancies, setVacancies] = useState<VacancyCard[]>([])

  useEffect(() => {
    if (accountDeleted) forget()
  }, [accountDeleted, forget])

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
      {accountDeleted && (
        <Alert tone="success">
          Sua conta foi excluída e seus dados pessoais foram apagados.
        </Alert>
      )}
      <HomeSearch vacancies={vacancies} />
      <TrustBar />
      <CategoryGrid vacancies={vacancies} />
      <OpenVacancies vacancies={vacancies} />

      <section id="como-funciona" aria-labelledby="como-funciona-titulo">
        <h2 id="como-funciona-titulo" className={SECTION_TITLE}>
          Como funciona
        </h2>
        <ol className="m-0 grid list-none grid-cols-1 gap-3 p-0 md:grid-cols-3">
          {STEPS.map(({ icon: Icon, color, title, body }, index) => (
            <li
              key={title}
              className="relative flex flex-col gap-4 overflow-hidden rounded-[24px] bg-ficha p-6"
            >
              <span
                className="absolute top-3 right-5 text-[64px] leading-none text-tinta/6 select-none"
                aria-hidden="true"
              >
                {index + 1}
              </span>
              <span
                className="grid size-12 place-items-center rounded-2xl text-white shadow-[0_8px_18px_rgb(32_32_32/14%)]"
                style={{ backgroundColor: color }}
                aria-hidden="true"
              >
                <Icon className="size-6" strokeWidth={1.5} />
              </span>
              <span className="flex flex-col gap-1">
                <span className="text-[15px] leading-6">{title}</span>
                <span className="text-[13px] leading-5 text-tinta-media">{body}</span>
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
          {SIDES.map(({ icon: Icon, gradient, title, body, action, to }) => (
            <li
              key={to}
              className="flex flex-col items-start gap-4 rounded-cartao border border-regua bg-papel p-6 md:p-8"
            >
              <span
                className="grid size-14 place-items-center rounded-2xl text-white shadow-[0_10px_22px_rgb(32_32_32/16%)]"
                style={{ backgroundImage: gradient }}
                aria-hidden="true"
              >
                <Icon className="size-7" strokeWidth={1.5} />
              </span>
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
