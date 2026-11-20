"""Hora extra (US52/US53): a empresa pede que o prestador fique mais tempo, antes do fim do turno.

O pedido nasce `AGUARDANDO_PRESTADOR` e expira sozinho se o prestador não responder em
`overtime_response_minutes` ou até o fim do turno (o que vier primeiro). Nada é cobrado no
pedido: a extensão só é paga em custódia quando o prestador aceita (US53). Recusar não tem
penalidade.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.core.notifications import notify, notify_company
from apps.core.state_machine import record_creation, transition
from apps.payments import services as payments
from apps.vacancies.history import format_brl
from apps.vacancies.models import Assignment, OvertimeRequest
from apps.vacancies.state_machine import OVERTIME_MACHINE
from integrations.payments import PaymentGatewayError

OT = OvertimeRequest.Status
S = Assignment.Status
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
MINUTE_OPTIONS = tuple(
    range(
        OvertimeRequest.MIN_MINUTES,
        OvertimeRequest.MAX_MINUTES + 1,
        OvertimeRequest.STEP_MINUTES,
    )
)


def minutes_label(minutes):
    """30 → '30 min'; 90 → '1 h 30 min'; 120 → '2 h'."""
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest} min"
    return f"{hours} h {rest} min" if rest else f"{hours} h"


def shift_minutes(vacancy):
    return max(1, int((vacancy.ends_at - vacancy.starts_at).total_seconds() // 60))


def min_amount_cents(vacancy, minutes):
    """Não paga menos que a hora do próprio turno: valor ÷ duração × extra (arredonda para cima)."""
    return -(-vacancy.pay_per_person_cents * minutes // shift_minutes(vacancy))


def options(vacancy):
    """Durações aceitas (30 min a 4 h, de 30 em 30) com o valor mínimo de cada uma."""
    return [
        {
            "minutes": minutes,
            "label": minutes_label(minutes),
            "min_amount_cents": min_amount_cents(vacancy, minutes),
        }
        for minutes in MINUTE_OPTIONS
    ]


def current_request(assignment):
    """O pedido mais recente da alocação (ou `None`). Aproveita `prefetch_related`."""
    requests = list(assignment.overtime_requests.all())
    return max(requests, key=lambda r: (r.created_at, r.pk)) if requests else None


def accepted_request(assignment):
    return next(
        (r for r in assignment.overtime_requests.all() if r.status == OT.ACCEPTED), None
    )


def serialize(request, params=None):
    if request is None:
        return None
    params = params or PlatformParameters.get()
    return {
        "id": request.pk,
        "assignment_id": request.assignment_id,
        "minutes": request.minutes,
        "minutes_label": minutes_label(request.minutes),
        "amount_cents": request.amount_cents,
        "net_cents": params.worker_net_cents(request.amount_cents),
        "status": request.status,
        "status_label": request.get_status_display(),
        "created_at": request.created_at.isoformat(),
        "expires_at": request.expires_at.isoformat(),
        "responded_at": request.responded_at and request.responded_at.isoformat(),
    }


def can_respond(request, now=None):
    """Botões "Aceitar"/"Recusar": pendente, dentro do prazo e com o turno em execução."""
    return (
        request is not None
        and request.status == OT.AWAITING
        and (now or timezone.now()) < request.expires_at
        and request.assignment.status == S.IN_PROGRESS
    )


def can_request(assignment, now=None):
    if assignment.status != S.IN_PROGRESS:
        return False
    if (now or timezone.now()) >= assignment.vacancy.ends_at:
        return False
    return not assignment.overtime_requests.filter(status__in=(OT.AWAITING, OT.ACCEPTED)).exists()


def clean(vacancy, minutes, amount_cents):
    # `bool` é subclasse de `int`: `true` no JSON não vale como 1 minuto.
    if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes not in MINUTE_OPTIONS:
        raise DomainError("Escolha de 30 min a 4 h, em passos de 30 min.")
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
        raise DomainError("Informe o valor da extensão.")
    minimum = min_amount_cents(vacancy, minutes)
    if amount_cents < minimum:
        raise DomainError(
            f"O valor mínimo para {minutes_label(minutes)} é {format_brl(minimum)} "
            "(proporcional ao valor por hora do turno)."
        )
    return minutes, amount_cents


@transaction.atomic
def request_overtime(assignment, *, minutes, amount_cents, actor=None, now=None):
    """Cria o pedido `AGUARDANDO_PRESTADOR` e avisa o prestador. Nada é cobrado aqui."""
    now = now or timezone.now()
    assignment = (
        Assignment.objects.select_for_update()
        .select_related("vacancy__company", "worker__user")
        .get(pk=assignment.pk)
    )
    vacancy = assignment.vacancy
    minutes, amount_cents = clean(vacancy, minutes, amount_cents)
    if assignment.status != S.IN_PROGRESS:
        raise DomainError("Só é possível pedir hora extra para um turno em execução.")
    if now >= vacancy.ends_at:
        raise DomainError("O turno já terminou: não é possível pedir hora extra.")
    if assignment.overtime_requests.filter(status=OT.AWAITING).exists():
        raise DomainError("Já existe um pedido de hora extra aguardando o prestador.")
    if assignment.overtime_requests.filter(status=OT.ACCEPTED).exists():
        raise DomainError("Este turno já foi estendido. Só é possível uma extensão por turno.")
    params = PlatformParameters.get()
    expires_at = min(now + timedelta(minutes=params.overtime_response_minutes), vacancy.ends_at)
    try:
        with transaction.atomic():
            request = OvertimeRequest.objects.create(
                assignment=assignment,
                minutes=minutes,
                amount_cents=amount_cents,
                requested_by=actor,
                created_at=now,
                expires_at=expires_at,
            )
    except IntegrityError:
        raise DomainError("Já existe um pedido de hora extra aguardando o prestador.") from None
    record_creation(
        request, OVERTIME_MACHINE, actor=actor, reason="Hora extra pedida pela empresa", now=now
    )
    deadline = expires_at.astimezone(LOCAL_TZ)
    notify(
        assignment.worker.user,
        "HORA_EXTRA",
        "Pedido de hora extra",
        f"{vacancy.company} pediu {minutes_label(minutes)} a mais em “{vacancy.title}” por "
        f"{format_brl(amount_cents)}. Responda até {deadline:%H:%M}.",
        link="/meus-trabalhos",
    )
    return request


def expire(request, *, now=None):
    """`AGUARDANDO_PRESTADOR → EXPIRADO`: nada é cobrado. Avisa a empresa."""
    request = transition(
        request,
        OVERTIME_MACHINE,
        OT.EXPIRED,
        reason="Sem resposta do prestador no prazo",
        now=now,
    )
    assignment = request.assignment
    notify_company(
        assignment.vacancy.company,
        "HORA_EXTRA",
        "Pedido de hora extra expirou",
        f"O prestador não respondeu ao pedido de {minutes_label(request.minutes)} a mais em "
        f"“{assignment.vacancy.title}”. Nada foi cobrado.",
    )
    return request


def overdue(now):
    return OvertimeRequest.objects.filter(status=OT.AWAITING, expires_at__lte=now).select_related(
        "assignment__vacancy__company"
    )


def _lock_pending(request, now, *, needs_running_shift):
    request = (
        OvertimeRequest.objects.select_for_update()
        .select_related("assignment__vacancy__company", "assignment__worker__user")
        .get(pk=request.pk)
    )
    if request.status != OT.AWAITING:
        raise DomainError("Este pedido de hora extra já foi respondido ou expirou.")
    if now >= request.expires_at:
        raise DomainError("Este pedido de hora extra expirou.")
    if needs_running_shift and request.assignment.status != S.IN_PROGRESS:
        raise DomainError("O turno não está mais em execução.")
    return request


def _payment_failed(request):
    """O PSP recusou a retenção: o pedido continua pendente e os dois são avisados."""
    request = OvertimeRequest.objects.select_related(
        "assignment__vacancy__company", "assignment__worker__user"
    ).get(pk=request.pk)
    vacancy = request.assignment.vacancy
    notify(
        request.assignment.worker.user,
        "HORA_EXTRA",
        "Não foi possível confirmar a hora extra",
        f"O pagamento da hora extra em “{vacancy.title}” não foi aprovado. O seu turno não foi "
        "estendido; tente aceitar de novo.",
        link="/meus-trabalhos",
    )
    notify_company(
        vacancy.company,
        "HORA_EXTRA",
        "Pagamento da hora extra falhou",
        f"O prestador aceitou a hora extra em “{vacancy.title}”, mas o pagamento da extensão "
        "não foi aprovado. O turno não foi estendido.",
    )


def accept(request, *, actor=None, now=None):
    """`AGUARDANDO_PRESTADOR → ACEITO`: a empresa paga a extensão em custódia e o turno estende.

    Se o PSP falhar, nada muda (o pedido segue pendente), os dois são avisados e sobe
    `DomainError`.
    """
    now = now or timezone.now()
    try:
        with transaction.atomic():
            request = _lock_pending(request, now, needs_running_shift=True)
            assignment = request.assignment
            vacancy = assignment.vacancy
            payments.retain_extension(vacancy.custody, request, actor=actor, now=now)
            request = transition(
                request,
                OVERTIME_MACHINE,
                OT.ACCEPTED,
                actor=actor,
                reason="Hora extra aceita pelo prestador",
                now=now,
                responded_at=now,
            )
            new_end = vacancy.ends_at + timedelta(minutes=request.minutes)
            Assignment.objects.filter(pk=assignment.pk).update(extended_until=new_end)
    except PaymentGatewayError:
        _payment_failed(request)
        raise DomainError(
            "Não foi possível confirmar o pagamento da hora extra. O turno não foi estendido."
        ) from None
    notify_company(
        vacancy.company,
        "HORA_EXTRA",
        "Hora extra aceita",
        f"O prestador aceitou {minutes_label(request.minutes)} a mais em “{vacancy.title}”. "
        f"O turno dele agora termina às {new_end.astimezone(LOCAL_TZ):%H:%M} e "
        f"{format_brl(request.amount_cents)} foram retidos em custódia.",
    )
    return request


@transaction.atomic
def decline(request, *, actor=None, now=None):
    """`AGUARDANDO_PRESTADOR → RECUSADO`, sem penalidade. Avisa a empresa."""
    now = now or timezone.now()
    request = _lock_pending(request, now, needs_running_shift=False)
    request = transition(
        request,
        OVERTIME_MACHINE,
        OT.DECLINED,
        actor=actor,
        reason="Hora extra recusada pelo prestador",
        now=now,
        responded_at=now,
    )
    vacancy = request.assignment.vacancy
    notify_company(
        vacancy.company,
        "HORA_EXTRA",
        "Hora extra recusada",
        f"O prestador recusou o pedido de {minutes_label(request.minutes)} a mais em "
        f"“{vacancy.title}”. Nada foi cobrado.",
    )
    return request
