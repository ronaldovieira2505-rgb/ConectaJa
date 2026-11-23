"""Histórico de demonstração para o `seed_demo`: turnos já realizados e a situação atual.

Tudo passa pelos mesmos serviços do sistema (vaga, candidatura, check-in, validação,
liquidação, avaliação), com o relógio voltado para o passado em cada passo. Assim os
lançamentos, a auditoria, a carteira, as avaliações e os indicadores ficam coerentes, como
se a plataforma estivesse em uso há algumas semanas.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import Notification, PlatformParameters
from apps.vacancies import application_services as applications
from apps.vacancies import assignment_services as assignments
from apps.vacancies import review_services as reviews
from apps.vacancies import services as vacancies
from apps.vacancies.models import Application, Assignment, Vacancy

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")

# Locais (rua, número, bairro, CEP, latitude, longitude). Endereços públicos de referência.
PLACES = {
    "vila-mariana": ("Rua Domingos de Morais", "1200", "Vila Mariana", "04010100",
                     "-23.589500", "-46.634600"),
    "mooca": ("Rua da Mooca", "2500", "Mooca", "03104002", "-23.555900", "-46.598700"),
    "itaim": ("Rua Joaquim Floriano", "466", "Itaim Bibi", "04534002",
              "-23.583900", "-46.676400"),
    "leopoldina": ("Avenida Mofarrej", "1200", "Vila Leopoldina", "05311000",
                   "-23.528600", "-46.733400"),
    "moema": ("Avenida Ibirapuera", "2120", "Moema", "04028001", "-23.604800", "-46.665300"),
    "brooklin": ("Rua Barão do Triunfo", "520", "Brooklin", "04602001",
                 "-23.617500", "-46.688900"),
    "tatuape": ("Rua Tuiuti", "1800", "Tatuapé", "03081000", "-23.541000", "-46.574600"),
    "pinheiros": ("Rua dos Pinheiros", "870", "Pinheiros", "05422001",
                  "-23.565200", "-46.684100"),
    "expo-norte": ("Rua José Bernardo Pinto", "333", "Vila Guilherme", "02055000",
                   "-23.512900", "-46.611500"),
    "butanta": ("Rua Alvarenga", "1500", "Butantã", "05509002", "-23.570900", "-46.711800"),
    "vila-olimpia": ("Rua Funchal", "500", "Vila Olímpia", "04551060",
                     "-23.593600", "-46.689900"),
}

# Índices das empresas em COMPANIES do seed_demo.
ARMAZENS, EVENTOS, OBRAS, MERCADO = 0, 1, 3, 4

# Cada turno: (dias atrás, hora local de início, duração em horas, empresa, local, vaga, equipe).
# Equipe: (e-mail do prestador, desfecho, nota da empresa, comentário da empresa,
#          nota do prestador, comentário do prestador). Nota None = ainda não avaliou.
# Desfechos: "ok" (empresa aprova as horas), "auto" (aprovação automática por prazo),
# "falta" (não fez check-in) e "contestada" (empresa contesta e o admin decide).
HISTORY = [
    (40, 7, 8, OBRAS, "vila-mariana", {
        "title": "Ajudante de obra em reforma de cozinha",
        "category": "AJUDANTE_OBRA",
        "description": "Retirada de azulejos antigos, transporte de entulho até a caçamba e "
        "apoio ao pedreiro no assentamento do piso novo.",
        "pay_per_person_cents": 17000, "positions": 2,
    }, [
        ("prestador1", "ok", 5, "Pontual e caprichosa. Deixou o canteiro organizado no fim "
         "do dia.", 5, "Equipe tranquila e o EPI foi entregue logo na chegada."),
        ("prestador5", "ok", 4, "Bom trabalho; precisou de orientação só no começo.", 4, ""),
    ]),
    (36, 6, 6, MERCADO, "mooca", {
        "title": "Repositor para inventário de fim de mês",
        "category": "VAREJO",
        "description": "Contagem e reposição de mercearia seca antes da abertura da loja, "
        "com conferência de validade.",
        "pay_per_person_cents": 12000, "positions": 3,
    }, [
        ("prestador2", "ok", 5, "Rápido e atento às validades.", 5,
         "Gerente muito educado e o pagamento caiu certinho."),
        ("prestador6", "ok", 5, "Excelente, queremos chamar de novo.", 4,
         "Turno puxado, mas bem organizado."),
        ("prestador4", "auto", None, "", 4, ""),
    ]),
    (33, 18, 6, EVENTOS, "itaim", {
        "title": "Garçom para coquetel de lançamento",
        "category": "EVENTOS",
        "description": "Serviço de bandeja em coquetel para 150 convidados. Traje: calça "
        "preta, camisa branca e sapato social.",
        "pay_per_person_cents": 16000, "positions": 3,
    }, [
        ("prestador1", "ok", 5, "Simpática com os convidados e muito profissional.", 5,
         "Evento bem organizado, recomendo."),
        ("prestador3", "ok", 4, "", 5, "Ótima coordenação no local."),
        ("prestador2", "ok", 4, "Cumpriu bem o combinado.", 5, ""),
    ]),
    (29, 22, 6, ARMAZENS, "leopoldina", {
        "title": "Descarga de contêiner no centro de distribuição",
        "category": "CARGA_DESCARGA",
        "description": "Descarga manual de caixas de até 20 kg e paletização por rota. "
        "Turno noturno, com lanche no intervalo.",
        "pay_per_person_cents": 17000, "positions": 2,
    }, [
        ("prestador5", "ok", 5, "Forte e cuidadoso com a carga frágil.", 4,
         "Turno noturno pesado, mas com água e lanche."),
        ("prestador2", "ok", 4, "", 4, ""),
    ]),
    (26, 8, 9, OBRAS, "moema", {
        "title": "Limpeza pós-obra de sala comercial",
        "category": "LIMPEZA",
        "description": "Limpeza fina após reforma: remoção de poeira, restos de tinta e "
        "lavagem de piso. Material fornecido.",
        "pay_per_person_cents": 16000, "positions": 2,
    }, [
        ("prestador4", "ok", 5, "Limpeza impecável, o cliente adorou.", 5,
         "Material de limpeza de qualidade."),
        ("prestador6", "ok", 4, "", 4, ""),
    ]),
    (22, 9, 5, EVENTOS, "brooklin", {
        "title": "Fotógrafo para confraternização de empresa",
        "category": "FOTOGRAFIA",
        "description": "Cobertura de confraternização com 80 pessoas: fotos espontâneas, "
        "foto oficial da equipe e entrega tratada em até 3 dias.",
        "pay_per_person_cents": 40000, "positions": 1,
    }, [
        ("prestador3", "ok", 5, "Fotos lindas e entregues antes do prazo.", 5,
         "Briefing claro e equipe receptiva."),
    ]),
    (19, 14, 6, MERCADO, "tatuape", {
        "title": "Operador de caixa para feirão de ofertas",
        "category": "VAREJO",
        "description": "Atendimento no caixa durante o feirão de fim de semana. "
        "Treinamento rápido no início do turno.",
        "pay_per_person_cents": 13500, "positions": 2,
    }, [
        ("prestador1", "contestada", 4, "Houve um mal-entendido sobre o horário de saída, "
         "resolvido com a equipe da plataforma.", 4, "O gerente confirmou que eu podia sair "
         "mais cedo; a plataforma resolveu rápido."),
        ("prestador4", "ok", 5, "Muito ágil no caixa.", 5, ""),
    ]),
    (15, 7, 9, OBRAS, "pinheiros", {
        "title": "Ajudante de obra para troca de piso",
        "category": "AJUDANTE_OBRA",
        "description": "Preparação de contrapiso, transporte de material e apoio no "
        "assentamento de porcelanato.",
        "pay_per_person_cents": 18000, "positions": 2,
    }, [
        ("prestador5", "ok", 5, "Mandou muito bem no assentamento.", 5,
         "Mestre de obras paciente e organizado."),
        ("prestador2", "ok", 4, "", 3, "Faltou água no canteiro à tarde."),
    ]),
    (12, 7, 10, EVENTOS, "expo-norte", {
        "title": "Montagem de estande em feira de tecnologia",
        "category": "EVENTOS",
        "description": "Montagem de painéis, iluminação e mobiliário de estande seguindo o "
        "projeto. Ferramentas fornecidas.",
        "pay_per_person_cents": 25000, "positions": 3,
    }, [
        ("prestador6", "ok", 5, "Ótima com montagem, muito cuidadosa.", 5, ""),
        ("prestador5", "ok", 4, "", 5, "Equipe de montagem muito unida."),
        ("prestador2", "falta", None, "", None, ""),
    ]),
    (9, 22, 6, ARMAZENS, "leopoldina", {
        "title": "Separação de pedidos para campanha de vendas",
        "category": "CARGA_DESCARGA",
        "description": "Separação e conferência de pedidos do e-commerce com coletor de "
        "dados. Turno noturno.",
        "pay_per_person_cents": 17000, "positions": 3,
    }, [
        ("prestador1", "ok", 5, "Separação sem nenhum erro.", 5,
         "Uma das empresas mais organizadas em que já trabalhei."),
        ("prestador4", "ok", 5, "", 4, ""),
        ("prestador3", "ok", 4, "Boa, mas poderia ser mais rápida na conferência.", 4, ""),
    ]),
    (6, 6, 6, MERCADO, "mooca", {
        "title": "Repositor de hortifrúti",
        "category": "VAREJO",
        "description": "Reposição de frutas e verduras, descarte de itens fora do padrão e "
        "organização das bancas.",
        "pay_per_person_cents": 12000, "positions": 2,
    }, [
        ("prestador3", "ok", 4, "", 4, ""),
        ("prestador6", "ok", 5, "Bancas sempre arrumadas.", 5, "Ambiente muito bom."),
    ]),
    (3, 8, 8, OBRAS, "butanta", {
        "title": "Pintura de muro e fachada",
        "category": "AJUDANTE_OBRA",
        "description": "Lixamento, aplicação de fundo e duas demãos de tinta acrílica em "
        "muro e fachada de sobrado. Andaime fornecido.",
        "pay_per_person_cents": 20000, "positions": 2,
    }, [
        # Avaliações do prestador em aberto: dá para demonstrar a US64 com estas contas.
        ("prestador1", "ok", 5, "Acabamento perfeito.", None, ""),
        ("prestador5", "ok", 5, "", None, ""),
    ]),
    (2, 18, 5, EVENTOS, "vila-olimpia", {
        "title": "Recepção em evento de premiação",
        "category": "EVENTOS",
        "description": "Recepção e credenciamento de convidados, orientação de fluxo e "
        "apoio ao cerimonial.",
        "pay_per_person_cents": 15000, "positions": 2,
    }, [
        # A empresa ainda não avaliou: dá para demonstrar a US63 com a empresa2.
        ("prestador4", "ok", None, "", 5, "Evento lindo e equipe muito acolhedora."),
        ("prestador3", "ok", None, "", None, ""),
    ]),
]

# Turno que terminou há poucas horas e espera a empresa conferir as horas.
AWAITING = (ARMAZENS, "leopoldina", {
    "title": "Conferência de mercadorias no recebimento",
    "category": "CARGA_DESCARGA",
    "description": "Conferência de notas e volumes no recebimento de fornecedores e "
    "organização das docas.",
    "pay_per_person_cents": 15000, "positions": 2,
}, ["prestador2", "prestador4"])

# Candidaturas em aberto nas vagas futuras: (título da vaga, prestadores na ordem em que se
# candidatam, quantos dos primeiros a empresa já aprovou). Na vaga de fotógrafo (1 posição)
# a segunda candidata fica na lista de espera.
OPEN_APPLICATIONS = [
    ("Apoio de salão em evento corporativo",
     ["prestador1", "prestador6", "prestador2", "prestador3"], 0),
    ("Montagem de evento na Paulista", ["prestador5", "prestador4"], 1),
    ("Fotógrafo para lançamento de produto", ["prestador3", "prestador6"], 1),
    ("Repositor para abastecimento de gôndolas", ["prestador6", "prestador3"], 0),
]


def _local(day, hour):
    return datetime.combine(day, time(hour, 0), tzinfo=LOCAL_TZ)


def _owner(company):
    return company.members.select_related("user").first().user


def _create_paid(company, place, data, starts_at, hours, now):
    street, number, district, zip_code, lat, lng = PLACES[place]
    vacancy = vacancies.create_vacancy(
        company=company,
        actor=_owner(company),
        now=now,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=hours),
        street=street,
        number=number,
        district=district,
        zip_code=zip_code,
        city="São Paulo",
        state="SP",
        latitude=lat,
        longitude=lng,
        **data,
    )
    return vacancies.pay_vacancy(vacancy, actor=_owner(company), now=now + timedelta(minutes=8))


def _staff(vacancy, crew, workers, created_at):
    """Candidaturas e aprovações da equipe, um dia depois da publicação."""
    owner = _owner(vacancy.company)
    staffed = []
    for i, key in enumerate(crew):
        worker = workers[key]
        applied_at = created_at + timedelta(hours=2 + i)
        application = applications.apply_to_vacancy(vacancy, worker, now=applied_at)
        Application.objects.filter(pk=application.pk).update(created_at=applied_at)
        applications.approve_application(
            application, actor=owner, now=created_at + timedelta(days=1, minutes=10 * i)
        )
        staffed.append(Assignment.objects.get(vacancy=vacancy, worker=worker))
    return staffed


def _start(vacancy, params):
    close_at = vacancy.starts_at - timedelta(minutes=params.applications_close_minutes_before)
    vacancy = vacancies.close_applications(vacancy, now=close_at)
    return vacancies.start_vacancy(vacancy, now=vacancy.starts_at)


def _work(assignment, vacancy, offset):
    """Check-in no local logo depois do início e check-out pouco antes do fim."""
    assignment = assignments.check_in(
        assignment,
        lat=vacancy.latitude,
        lng=vacancy.longitude,
        actor=assignment.worker.user,
        now=vacancy.starts_at + timedelta(seconds=40 + offset),
    )
    return assignments.check_out(
        assignment,
        actor=assignment.worker.user,
        now=vacancy.ends_at - timedelta(minutes=4 + offset % 7),
    )


def _run_shift(vacancy, crew, workers, admin, params):
    owner = _owner(vacancy.company)
    staffed = _staff(vacancy, [c[0] for c in crew], workers, vacancy.created_at)
    vacancy = _start(Vacancy.objects.get(pk=vacancy.pk), params)
    contest_window = timedelta(minutes=params.contest_window_minutes)
    for i, (assignment, spec) in enumerate(zip(staffed, crew, strict=True)):
        key, outcome, co_rating, co_comment, w_rating, w_comment = spec
        if outcome == "falta":
            tolerance = timedelta(minutes=params.no_show_tolerance_minutes + 1)
            assignments.mark_no_show(assignment, now=vacancy.starts_at + tolerance)
            continue
        assignment = _work(assignment, vacancy, i)
        done_at = assignment.check_out_at
        if outcome == "ok":
            assignment = assignments.approve_hours(
                assignment, actor=owner, now=done_at + timedelta(minutes=50)
            )
        elif outcome == "auto":
            assignment = assignments.auto_approve_hours(
                assignment, now=done_at + contest_window + timedelta(minutes=1)
            )
        elif outcome == "contestada":
            assignment = assignments.contest(
                assignment,
                reason="O prestador saiu antes do horário combinado.",
                actor=owner,
                now=done_at + timedelta(seconds=30),
            )
            assignment = assignments.resolve_contest(
                assignment,
                in_favor_of_worker=True,
                reason="O gerente da loja confirmou que liberou a saída antecipada.",
                actor=admin,
                now=done_at + timedelta(hours=20),
            )
        settled_at = assignment.validated_at + timedelta(minutes=30)
        assignment = assignments.settle(assignment, now=settled_at)
        if co_rating:
            reviews.review_worker(
                assignment,
                author=owner,
                rating=co_rating,
                comment=co_comment,
                now=settled_at + timedelta(hours=3),
            )
        if w_rating:
            reviews.review_company(
                assignment,
                author=workers[key].user,
                rating=w_rating,
                comment=w_comment,
                now=settled_at + timedelta(hours=5),
            )
    vacancy = Vacancy.objects.get(pk=vacancy.pk)
    finish_at = max(vacancy.ends_at, vacancy.starts_at) + timedelta(days=1, hours=2)
    vacancies.finalize_vacancy(vacancy, now=finish_at)


def build_history(companies, workers, admin, now):
    """Turnos realizados nas últimas semanas. Idempotente: roda uma vez por banco."""
    first_title = HISTORY[0][5]["title"]
    if Vacancy.objects.filter(company=companies[OBRAS], title=first_title).exists():
        return False
    params = PlatformParameters.get()
    before = Notification.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
    today = timezone.localdate(now)
    for days_ago, hour, hours, company_index, place, data, crew in HISTORY:
        starts_at = _local(today - timedelta(days=days_ago), hour)
        published_at = starts_at - timedelta(days=4, hours=3)
        vacancy = _create_paid(companies[company_index], place, data, starts_at, hours,
                               published_at)
        _run_shift(vacancy, crew, workers, admin, params)
    # Os avisos do histórico teriam a data de hoje e lotariam o sino: ficam só os atuais.
    Notification.objects.filter(pk__gt=before).delete()
    return True


def build_current_state(companies, workers, now):
    """Turno à espera de validação e candidaturas em aberto nas vagas futuras."""
    company_index, place, data, crew = AWAITING
    company = companies[company_index]
    # Sem turno em andamento com esse título (o anterior já foi aprovado e pago), cria outro:
    # assim "Confirmar presença" sempre tem o que mostrar na demonstração.
    in_progress = Vacancy.objects.filter(
        company=company, title=data["title"], status=Vacancy.Status.IN_PROGRESS
    )
    if not in_progress.exists():
        params = PlatformParameters.get()
        starts_at = (now - timedelta(hours=10)).replace(minute=0, second=0, microsecond=0)
        try:
            with transaction.atomic():
                vacancy = _create_paid(company, place, data, starts_at, 6,
                                       starts_at - timedelta(days=3))
                staffed = _staff(vacancy, crew, workers, vacancy.created_at)
                vacancy = _start(Vacancy.objects.get(pk=vacancy.pk), params)
                for i, assignment in enumerate(staffed):
                    _work(assignment, vacancy, i)
        except DomainError:
            pass  # conflito de horário de algum prestador: segue sem esse turno

    for title, keys, approve_first in OPEN_APPLICATIONS:
        vacancy = (
            Vacancy.objects.filter(
                title=title, status=Vacancy.Status.PUBLISHED, starts_at__gt=now
            )
            .order_by("-pk")
            .first()
        )
        if vacancy is None or vacancy.applications.exists():
            continue
        created = []
        for i, key in enumerate(keys):
            applied_at = now - timedelta(hours=20 - 3 * i)
            try:
                application = applications.apply_to_vacancy(vacancy, workers[key], now=now)
            except DomainError:
                continue  # conflito de horário ou vaga lotada: não força
            Application.objects.filter(pk=application.pk).update(created_at=applied_at)
            created.append(application)
        for application in created[:approve_first]:
            applications.approve_application(
                application, actor=_owner(vacancy.company), now=now
            )
