"""Serviço de domínio da Alocação: execução, validação e liquidação."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters, StateTransition
from apps.core.notifications import notify, notify_admins, notify_company
from apps.core.state_machine import transition
from apps.payments import services as payments
from apps.vacancies.models import Assignment
from apps.vacancies.state_machine import ASSIGNMENT_MACHINE
from apps.workers.services import apply_automatic_suspension
from integrations.geo import haversine_distance_m

S = Assignment.Status


def _validated_coordinate(value, name, limit):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise DomainError(f"{name} inválida.") from None
    if not number.is_finite() or abs(number) > limit:
        raise DomainError(f"{name} fora da faixa válida.")
    return number.quantize(Decimal("0.000001"))


@transaction.atomic
def check_in(assignment, *, lat, lng, actor=None, now=None):
    now = now or timezone.now()
    lat = _validated_coordinate(lat, "Latitude", 90)
    lng = _validated_coordinate(lng, "Longitude", 180)
    ASSIGNMENT_MACHINE.validate(assignment.status, S.IN_PROGRESS)
    params = PlatformParameters.get()
    vacancy = assignment.vacancy
    opens_at = vacancy.starts_at - timedelta(minutes=params.checkin_open_minutes_before)
    closes_at = vacancy.starts_at + timedelta(minutes=params.no_show_tolerance_minutes)
    if not opens_at <= now <= closes_at:
        raise DomainError("O check-in está fora da janela permitida.")
    distance = haversine_distance_m(lat, lng, vacancy.latitude, vacancy.longitude)
    if distance > params.geofence_radius_m:
        raise DomainError(
            f"Você está a {round(distance)} m do local. Aproxime-se para registrar a chegada."
        )
    return transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.IN_PROGRESS,
        actor=actor,
        reason="Check-in realizado",
        now=now,
        check_in_at=now,
        check_in_lat=lat,
        check_in_lng=lng,
        check_in_distance_m=round(distance),
    )


@transaction.atomic
def check_out(assignment, *, actor=None, now=None):
    now = now or timezone.now()
    return transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.AWAITING_VALIDATION,
        actor=actor,
        reason="Check-out realizado",
        now=now,
        check_out_at=now,
    )


@transaction.atomic
def auto_check_out(assignment, *, now=None):
    return transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.AWAITING_VALIDATION,
        reason="Check-out automático",
        now=now,
        check_out_at=assignment.vacancy.ends_at,
        check_out_auto=True,
    )


@transaction.atomic
def mark_no_show(assignment, *, now=None):
    """Falta: libera a posição, reabre a vaga, avisa a empresa e avalia a suspensão."""
    now = now or timezone.now()
    assignment = transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.NO_SHOW,
        reason="Sem check-in dentro da tolerância",
        now=now,
    )
    vacancy = assignment.vacancy
    if now < vacancy.ends_at and not vacancy.reopened:
        vacancy.reopened = True
        vacancy.save(update_fields=["reopened"])
    notify_company(
        vacancy.company,
        "FALTA",
        "Prestador faltou",
        f"Um prestador não compareceu a “{vacancy.title}”. A vaga foi reaberta.",
    )
    apply_automatic_suspension(assignment.worker, now=now)
    return assignment


@transaction.atomic
def approve_hours(assignment, *, actor=None, now=None):
    now = now or timezone.now()
    assignment = transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.APPROVED,
        actor=actor,
        reason="Horas aprovadas pela empresa",
        now=now,
        validated_at=now,
        validated_by=actor,
    )
    notify(
        assignment.worker.user,
        "HORAS_APROVADAS",
        "Horas aprovadas",
        f"A empresa aprovou as suas horas em “{assignment.vacancy.title}”. "
        "O pagamento será liberado.",
    )
    return assignment


@transaction.atomic
def auto_approve_hours(assignment, *, now=None):
    now = now or timezone.now()
    assignment = transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.APPROVED,
        reason="aprovação por decurso de prazo",
        now=now,
        validated_at=now,
        validated_by=None,
    )
    vacancy = assignment.vacancy
    notify(
        assignment.worker.user,
        "HORAS_APROVADAS",
        "Horas aprovadas automaticamente",
        f"As horas de “{vacancy.title}” foram aprovadas por decurso de prazo. "
        "O pagamento será liberado.",
    )
    notify_company(
        vacancy.company,
        "HORAS_APROVADAS",
        "Horas aprovadas automaticamente",
        f"O prazo para conferir as horas de “{vacancy.title}” terminou sem manifestação. "
        "As horas foram aprovadas e o pagamento será liberado.",
    )
    return assignment


@transaction.atomic
def contest(assignment, *, reason, actor=None, now=None):
    if not reason.strip():
        raise DomainError("Informe o motivo da contestação.")
    assignment = transition(
        assignment, ASSIGNMENT_MACHINE, S.CONTESTED, actor=actor, reason=reason, now=now
    )
    message = f"A empresa contestou as horas de “{assignment.vacancy.title}”."
    notify(assignment.worker.user, "CONTESTACAO", "Horas contestadas", message)
    notify_admins("CONTESTACAO", "Nova contestação", message)
    return assignment


@transaction.atomic
def resolve_contest(assignment, *, in_favor_of_worker, reason, actor, now=None):
    """Admin decide: a favor do prestador → APROVADA; da empresa → ESTORNADA."""
    if not reason.strip():
        raise DomainError("O motivo é obrigatório.")
    if in_favor_of_worker:
        return transition(
            assignment,
            ASSIGNMENT_MACHINE,
            S.APPROVED,
            actor=actor,
            reason=reason,
            now=now,
            validated_at=now or timezone.now(),
            validated_by=actor,
        )
    ASSIGNMENT_MACHINE.validate(assignment.status, S.REFUNDED)
    payments.refund_assignment(
        assignment.vacancy.custody, assignment, actor=actor, reason=reason, now=now
    )
    return transition(
        assignment, ASSIGNMENT_MACHINE, S.REFUNDED, actor=actor, reason=reason, now=now
    )


def free_cancel_message(params):
    minutes = params.free_cancel_minutes_before
    window = f"{minutes // 60} h" if minutes % 60 == 0 else f"{minutes} min"
    return f"Cancelamentos só podem ser feitos até {window} antes do início. Fale com o suporte."


def ensure_free_cancel_window(vacancy, *, now):
    """Dentro do prazo (`free_cancel_minutes_before`) a empresa não cancela pelo app."""
    params = PlatformParameters.get()
    if vacancy.starts_at - now < timedelta(minutes=params.free_cancel_minutes_before):
        raise DomainError(free_cancel_message(params))


def clean_cancel_reason(reason):
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("Informe o motivo do cancelamento.")
    return reason


@transaction.atomic
def cancel_confirmed_by_company(assignment, *, reason, actor=None, now=None):
    """CONFIRMADA → CANCELADA_EMPRESA: estorna a posição e avisa o prestador.

    Sem checar o prazo nem o motivo; quem chama (cancelamento da alocação ou da vaga
    inteira) valida antes.
    """
    ASSIGNMENT_MACHINE.validate(assignment.status, S.CANCELLED_BY_COMPANY)
    payments.refund_assignment(
        assignment.vacancy.custody, assignment, actor=actor, reason=reason, now=now
    )
    assignment = transition(
        assignment, ASSIGNMENT_MACHINE, S.CANCELLED_BY_COMPANY, actor=actor, reason=reason, now=now
    )
    notify(
        assignment.worker.user,
        "TURNO_CANCELADO",
        "Turno cancelado pela empresa",
        f"A empresa cancelou o seu turno em “{assignment.vacancy.title}”. "
        f"Motivo: {reason}",
        link="/meus-trabalhos",
    )
    return assignment


@transaction.atomic
def cancel_by_company(assignment, *, reason, actor=None, now=None):
    """Empresa cancela uma alocação confirmada com antecedência (US71)."""
    now = now or timezone.now()
    reason = clean_cancel_reason(reason)
    ASSIGNMENT_MACHINE.validate(assignment.status, S.CANCELLED_BY_COMPANY)
    ensure_free_cancel_window(assignment.vacancy, now=now)
    return cancel_confirmed_by_company(assignment, reason=reason, actor=actor, now=now)


def is_late_worker_cancel(vacancy, *, now, params=None):
    """Cancelamento tardio: falta menos que `free_cancel_minutes_before` para o início."""
    params = params or PlatformParameters.get()
    return vacancy.starts_at - now < timedelta(minutes=params.free_cancel_minutes_before)


def late_cancel_warning(params):
    days = params.late_cancel_block_days
    unit = "dia" if days == 1 else "dias"
    return f"Cancelando agora você fica {days} {unit} sem poder se candidatar."


@transaction.atomic
def cancel_by_worker(assignment, *, actor=None, now=None):
    """Prestador cancela a própria alocação confirmada (US72).

    Com antecedência: sem penalidade. Tardio: bloqueio por `late_cancel_block_days`
    (`suspended_until`). Em ambos libera a posição; se a candidatura já estava encerrada,
    reabre a vaga (selo "Urgente"). Não conta como falta.
    """
    now = now or timezone.now()
    ASSIGNMENT_MACHINE.validate(assignment.status, S.CANCELLED_BY_WORKER)
    params = PlatformParameters.get()
    vacancy = assignment.vacancy
    late = is_late_worker_cancel(vacancy, now=now, params=params)
    assignment = transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.CANCELLED_BY_WORKER,
        actor=actor,
        reason="Cancelamento tardio" if late else "Cancelamento com antecedência",
        now=now,
    )
    close_at = vacancy.starts_at - timedelta(minutes=params.applications_close_minutes_before)
    if now >= close_at and now < vacancy.ends_at and not vacancy.reopened:
        vacancy.reopened = True
        vacancy.save(update_fields=["reopened"])
    worker = assignment.worker
    if late:
        block_until = now + timedelta(days=params.late_cancel_block_days)
        if worker.suspended_until is None or worker.suspended_until < block_until:
            worker.suspended_until = block_until
            worker.save(update_fields=["suspended_until"])
        StateTransition.objects.create(
            entity_type="WorkerSuspension",
            entity_id=worker.pk,
            from_state="ATIVO",
            to_state="SUSPENSO",
            actor=actor,
            reason="Cancelamento tardio",
            created_at=now,
        )
        notify(
            worker.user,
            "CANCELAMENTO_TARDIO",
            "Cancelamento tardio",
            f"Você cancelou “{vacancy.title}” em cima da hora e não poderá se candidatar "
            f"por {params.late_cancel_block_days} dias.",
            link="/meus-trabalhos",
        )
    else:
        notify(
            worker.user,
            "TURNO_CANCELADO",
            "Participação cancelada",
            f"Você cancelou a sua participação em “{vacancy.title}” sem penalidade.",
            link="/meus-trabalhos",
        )
    notify_company(
        vacancy.company,
        "CANCELAMENTO_PRESTADOR",
        "Prestador cancelou",
        f"Um prestador cancelou a participação em “{vacancy.title}”. "
        "A posição foi liberada para novas candidaturas.",
    )
    return assignment


@transaction.atomic
def settle(assignment, *, now=None):
    """APROVADA → PAGA. Se o PSP falhar, a exceção desfaz tudo e segue APROVADA."""
    ASSIGNMENT_MACHINE.validate(assignment.status, S.PAID)
    payments.settle_assignment(assignment.vacancy.custody, assignment, now=now)
    assignment = transition(
        assignment, ASSIGNMENT_MACHINE, S.PAID, reason="Liquidação do turno", now=now
    )
    notify(
        assignment.worker.user,
        "PAGAMENTO_LIBERADO",
        "Pagamento liberado",
        f"O pagamento de “{assignment.vacancy.title}” foi liberado.",
    )
    return assignment
