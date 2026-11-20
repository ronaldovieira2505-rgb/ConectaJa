"""Justificar a chegada quando o check-in pelo celular não funciona (US51).

Fluxo: o prestador envia (dentro da janela de check-in) → a empresa confirma a chegada ou recusa
→ sem resposta até o fim do turno, o pedido vai para o admin, que decide entre presença e falta.
Enquanto o pedido está com a empresa ou com o admin, a falta automática fica suspensa.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.core.notifications import notify, notify_admins, notify_company
from apps.core.state_machine import transition
from apps.vacancies import assignment_services as assignments
from apps.vacancies.models import ArrivalJustification, Assignment
from apps.vacancies.state_machine import ASSIGNMENT_MACHINE

J = ArrivalJustification.Status
S = Assignment.Status
# Pedidos que ainda suspendem a falta automática.
OPEN_STATUSES = (J.PENDING, J.ADMIN)


def checkin_window(assignment, params=None):
    params = params or PlatformParameters.get()
    starts = assignment.vacancy.starts_at
    return (
        starts - timedelta(minutes=params.checkin_open_minutes_before),
        starts + timedelta(minutes=params.no_show_tolerance_minutes),
    )


def can_justify(assignment, now=None, params=None):
    """`CONFIRMADA`, dentro da janela de check-in e sem justificativa anterior."""
    if assignment.status != S.CONFIRMED:
        return False
    if ArrivalJustification.objects.filter(assignment=assignment).exists():
        return False
    opens, closes = checkin_window(assignment, params)
    return opens <= (now or timezone.now()) <= closes


def clean(reason, text):
    if reason not in ArrivalJustification.Reason.values:
        raise DomainError("Escolha o motivo da lista.")
    text = (text or "").strip() if isinstance(text, str) or text is None else None
    if text is None:
        raise DomainError("Explicação inválida.")
    if len(text) > ArrivalJustification.TEXT_MAX_LENGTH:
        raise DomainError("A explicação pode ter no máximo 300 caracteres.")
    if reason == ArrivalJustification.Reason.OTHER and not text:
        raise DomainError("Explique o que aconteceu.")
    return reason, text


@transaction.atomic
def submit(assignment, *, reason, text="", now=None):
    """Uma justificativa por alocação, só dentro da janela de check-in. Avisa a empresa."""
    now = now or timezone.now()
    reason, text = clean(reason, text)
    assignment = (
        Assignment.objects.select_for_update()
        .select_related("vacancy__company")
        .get(pk=assignment.pk)
    )
    if assignment.status != S.CONFIRMED:
        raise DomainError("Só é possível justificar a chegada de um turno confirmado.")
    if ArrivalJustification.objects.filter(assignment=assignment).exists():
        raise DomainError("Você já enviou uma justificativa para este turno.")
    opens, closes = checkin_window(assignment)
    if not opens <= now <= closes:
        raise DomainError("A justificativa só pode ser enviada na janela de check-in.")
    try:
        with transaction.atomic():
            justification = ArrivalJustification.objects.create(
                assignment=assignment, reason=reason, text=text, created_at=now
            )
    except IntegrityError:
        raise DomainError("Você já enviou uma justificativa para este turno.") from None
    vacancy = assignment.vacancy
    notify_company(
        vacancy.company,
        "JUSTIFICATIVA_CHEGADA",
        "Prestador não conseguiu registrar a chegada",
        f"{assignment.worker.full_name.split()[0]} justificou a chegada em “{vacancy.title}”: "
        f"{justification.get_reason_display()}. Confirme ou recuse em “Confirmar presença”.",
        link="/empresa/confirmar-presenca",
    )
    return justification


def _ensure_waiting(justification):
    # O prestador pode ter conseguido registrar a chegada depois de enviar o pedido.
    if justification.assignment.status != S.CONFIRMED:
        raise DomainError("Este turno não está mais aguardando a chegada.")


def _confirm(justification, *, actor, reason, now):
    """Chegada confirmada: `CONFIRMADA → EM_EXECUCAO` com o horário do pedido como check-in."""
    assignment = justification.assignment
    transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.IN_PROGRESS,
        actor=actor,
        reason="Check-in confirmado pela empresa" if reason is None else reason,
        now=now,
        check_in_at=justification.created_at,
        check_in_confirmed_by_company=True,
    )
    justification.status = J.CONFIRMED
    justification.decided_at, justification.decided_by = now, actor
    justification.decision_reason = reason or ""
    justification.save(update_fields=["status", "decided_at", "decided_by", "decision_reason"])
    notify(
        assignment.worker.user,
        "JUSTIFICATIVA_CHEGADA",
        "Chegada confirmada",
        f"A sua chegada em “{assignment.vacancy.title}” foi confirmada.",
        link="/meus-trabalhos",
    )


@transaction.atomic
def decide_by_company(justification, *, confirm, reason="", actor=None, now=None):
    """A empresa confirma a chegada ou recusa com motivo (só enquanto `PENDENTE`)."""
    now = now or timezone.now()
    justification = (
        ArrivalJustification.objects.select_for_update()
        .select_related("assignment__vacancy", "assignment__worker__user")
        .get(pk=justification.pk)
    )
    if justification.status != J.PENDING:
        raise DomainError("Esta justificativa já foi decidida.")
    _ensure_waiting(justification)
    reason = (reason or "").strip()
    if confirm:
        _confirm(justification, actor=actor, reason=None, now=now)
        return justification
    if not reason:
        raise DomainError("Informe o motivo da recusa.")
    justification.status = J.REFUSED
    justification.decided_at, justification.decided_by = now, actor
    justification.decision_reason = reason
    justification.save(update_fields=["status", "decided_at", "decided_by", "decision_reason"])
    assignment = justification.assignment
    notify(
        assignment.worker.user,
        "JUSTIFICATIVA_CHEGADA",
        "Justificativa de chegada recusada",
        f"A empresa recusou a sua justificativa em “{assignment.vacancy.title}”. Motivo: {reason}",
        link="/meus-trabalhos",
    )
    return justification


def escalate_overdue(now=None):
    """Sem resposta da empresa até o fim do turno: o pedido vai para o admin. Idempotente."""
    now = now or timezone.now()
    overdue = ArrivalJustification.objects.filter(
        status=J.PENDING,
        assignment__status=S.CONFIRMED,
        assignment__vacancy__ends_at__lte=now,
    ).select_related("assignment__vacancy")
    count = 0
    for justification in overdue:
        updated = ArrivalJustification.objects.filter(pk=justification.pk, status=J.PENDING).update(
            status=J.ADMIN
        )
        if not updated:
            continue
        count += 1
        notify_admins(
            "JUSTIFICATIVA_CHEGADA",
            "Justificativa de chegada sem resposta da empresa",
            f"Decida entre presença e falta na alocação #{justification.assignment_id} "
            f"(“{justification.assignment.vacancy.title}”).",
        )
    return count


@transaction.atomic
def decide_by_admin(justification, *, presence, actor, now=None):
    """O admin decide entre presença (chegada confirmada) e falta (US55)."""
    now = now or timezone.now()
    justification = (
        ArrivalJustification.objects.select_for_update()
        .select_related("assignment__vacancy", "assignment__worker__user")
        .get(pk=justification.pk)
    )
    if justification.status != J.ADMIN:
        raise DomainError("Esta justificativa não está com a equipe.")
    _ensure_waiting(justification)
    if presence:
        _confirm(justification, actor=actor, reason="Presença confirmada pelo admin", now=now)
        return justification
    justification.status = J.REFUSED
    justification.decided_at, justification.decided_by = now, actor
    justification.decision_reason = "Falta confirmada pelo admin"
    justification.save(update_fields=["status", "decided_at", "decided_by", "decision_reason"])
    assignments.mark_no_show(
        justification.assignment, now=now, actor=actor, reason="Falta confirmada pelo admin"
    )
    return justification
