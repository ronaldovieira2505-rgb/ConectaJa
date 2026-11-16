import { ArrowRight, ArrowUpRight, BadgeCheck, MapPin, Scale, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import Disclosure, { type DisclosureItem } from '../components/landing/Disclosure'
import Hero from '../components/landing/Hero'
import OpenVacancies from '../components/landing/OpenVacancies'

const STEPS: DisclosureItem[] = [
  {
    title: 'A empresa publica e paga',
    body: <p>O valor do turno fica retido em custódia antes de a vaga aparecer na busca.</p>,
  },
  {
    title: 'O prestador se candidata',
    body: <p>Ele vê quanto vai receber e as regras do turno. A empresa escolhe quem aprovar.</p>,
  },
  {
    title: 'Presença confirmada, repasse feito',
    body: <p>Check-in e check-out por localização. Horas confirmadas, o valor segue por PIX.</p>,
  },
]

const GUARANTEES = [
  { icon: ShieldCheck, title: 'Pagamento em custódia', body: 'A vaga só é publicada depois de paga.' },
  { icon: BadgeCheck, title: 'Cadastros verificados', body: 'CNPJ, documento, selfie e PIX do titular.' },
  { icon: MapPin, title: 'Presença por localização', body: 'O check-in só vale no endereço do turno.' },
  { icon: Scale, title: 'Regras iguais para os dois', body: 'Prazos conhecidos antes da candidatura.' },
]

const QUESTIONS: DisclosureItem[] = [
  {
    title: 'Quanto custa para a empresa?',
    body: (
      <p>
        A empresa paga exatamente o valor anunciado, sem mensalidade nem acréscimo. A taxa da
        plataforma é descontada do repasse ao prestador e aparece em cada vaga.
      </p>
    ),
  },
  {
    title: 'Quando o prestador recebe?',
    body: (
      <p>
        Depois do check-out, quando a empresa confirma as horas. Se ela não responder dentro do
        prazo, a aprovação é automática e o valor vai para a carteira.
      </p>
    ),
  },
  {
    title: 'E se alguém faltar?',
    body: (
      <p>
        A falta é registrada depois da tolerância, a posição volta para a busca como urgente e o
        valor retido não é repassado. Faltas repetidas suspendem o cadastro.
      </p>
    ),
  },
  {
    title: 'Dá para cancelar?',
    body: (
      <p>
        Sim. Com antecedência não há penalidade para nenhum dos lados, e a empresa recebe o
        estorno. Os prazos aparecem na vaga antes da candidatura.
      </p>
    ),
  },
  {
    title: 'Quem pode se cadastrar?',
    body: (
      <p>
        Empresas com CNPJ ativo e pessoas físicas maiores de 18 anos, com documento com foto,
        selfie e chave PIX própria. Todo cadastro passa por verificação.
      </p>
    ),
  },
  {
    title: 'O pagamento já é real?',
    body: (
      <p>
        Ainda não. Nesta versão o pagamento é simulado: o fluxo de custódia e repasse é o mesmo,
        mas nenhum valor é cobrado de verdade.
      </p>
    ),
  },
]

const TEXT_COLUMN = 'flex flex-col items-start gap-5 px-1 md:px-0 md:py-4 xl:gap-6 xl:p-6'
const ARROW = 'size-4 shrink-0 transition-transform duration-200 motion-reduce:transition-none'

/** Página inicial pública: explica a proposta para os dois lados e leva ao cadastro ou à busca. */
export default function LandingPage() {
  return (
    <div className="flex flex-col gap-secao">
      <div className="flex flex-col gap-6 md:gap-10">
        <Hero
          title="Turno combinado, pagamento garantido"
          caption="Turnos curtos de trabalho manual. O valor fica retido antes de o turno começar e é liberado com a presença confirmada."
          notice="Só aparece na busca a vaga que já foi paga."
        />
        <OpenVacancies />
        <div className="flex flex-wrap justify-center gap-2">
          <Link to="/vagas" className="btn btn-primary">
            Ver vagas abertas
          </Link>
          <Link to="/cadastro/empresa" className="btn btn-secondary">
            Publicar um turno
          </Link>
        </div>
      </div>

      <section
        id="como-funciona"
        aria-labelledby="como-funciona-titulo"
        className="grid grid-cols-1 gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] md:gap-coluna xl:grid-cols-3 [&>*]:min-w-0"
      >
        <div className={TEXT_COLUMN}>
          <h2 id="como-funciona-titulo" className="m-0 text-[28px] leading-8">
            Do anúncio ao PIX em três passos.
          </h2>
          <p className="m-0">
            Cada etapa tem um responsável e um prazo. Nada fica parado esperando alguém lembrar.
          </p>
          <Disclosure name="passos" items={STEPS} />
          <Link to="/cadastro/prestador" className="btn btn-secondary group gap-4">
            Quero trabalhar <ArrowRight className={`${ARROW} group-hover:translate-x-0.5`} strokeWidth={1.25} aria-hidden="true" />
          </Link>
        </div>
        <div className="superficie-gradiente relative flex aspect-[904/640] w-full flex-col justify-end gap-2 overflow-hidden rounded-cartao p-5 md:self-center md:p-8 xl:col-span-2 xl:aspect-[904/516] xl:self-start">
          {['Vaga publicada e paga', 'Candidatura aprovada', 'Check-out confirmado'].map(
            (label, index) => (
              <p
                key={label}
                className="m-0 flex w-fit items-center gap-3 rounded-full bg-vidro py-2 pr-5 pl-2 text-[13px] leading-4 backdrop-blur-flutuante"
                style={{ marginLeft: `${index * 8}%` }}
              >
                <span className="grid size-6 place-items-center rounded-full bg-tinta text-[11px] text-papel">
                  {index + 1}
                </span>
                {label}
              </p>
            ),
          )}
        </div>
      </section>

      <section
        id="para-quem"
        aria-labelledby="para-quem-titulo"
        className="grid grid-cols-1 gap-8 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] md:gap-coluna xl:grid-cols-3 [&>*]:min-w-0"
      >
        <ul className="m-0 grid list-none grid-cols-1 gap-x-coluna gap-y-8 rounded-cartao bg-ficha p-6 min-[480px]:grid-cols-2 md:self-center md:p-10 xl:col-span-2 xl:self-start">
          {GUARANTEES.map(({ icon: Icon, title, body }) => (
            <li key={title} className="flex flex-col gap-2">
              <Icon className="mb-2 size-6" strokeWidth={1.25} aria-hidden="true" />
              <h3 className="m-0 text-[15px] leading-6 tracking-normal">{title}</h3>
              <p className="m-0 text-[13px] leading-6 text-tinta-media">{body}</p>
            </li>
          ))}
        </ul>
        <div className={TEXT_COLUMN}>
          <h2 id="para-quem-titulo" className="m-0 text-[28px] leading-8">
            Dois lados.
            <br />O mesmo combinado.
          </h2>
          <p className="m-0">
            Para a empresa: publicar o turno em minutos, escolher entre candidatos verificados e
            pagar só o valor anunciado.
          </p>
          <p className="m-0">
            Para o prestador: saber quanto recebe antes de se candidatar, com o pagamento já
            garantido.
          </p>
          <Link to="/cadastro/empresa" className="btn btn-secondary group gap-4">
            Cadastrar minha empresa{' '}
            <ArrowUpRight className={`${ARROW} group-hover:translate-x-0.5`} strokeWidth={1.25} aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section
        id="perguntas"
        aria-labelledby="perguntas-titulo"
        className="grid grid-cols-1 gap-8 md:grid-cols-3 md:gap-coluna [&>*]:min-w-0"
      >
        <div className="flex flex-col gap-4 px-1 md:gap-6 md:px-0">
          <h2 id="perguntas-titulo" className="m-0 text-[28px] leading-8 text-balance">
            Você deve ter algumas perguntas.
          </h2>
          <p className="m-0 text-tinta-media">Sobre o pagamento, as regras e o cadastro.</p>
        </div>
        <div className="md:col-span-2">
          <Disclosure name="perguntas" items={QUESTIONS} size="large" />
        </div>
      </section>
    </div>
  )
}
