"""Lista de espera (US43): candidaturas pendentes de uma vaga cuja equipe está completa.

A ordem é a da candidatura. Quando uma posição é liberada por falta (US55) ou por cancelamento
do prestador (US72), o primeiro elegível é aprovado automaticamente pelo SISTEMA.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.vacancies import application_services as applications
from apps.vacancies.models import Application, Vacancy
from apps.workers.models import Worker

V = Vacancy.Status

CALLABLE_VACANCY_STATUSES = (V.PUBLISHED, V.APPLICATIONS_CLOSED, V.IN_PROGRESS)


def is_team_complete(vacancy):
    return vacancy.unavailable_positions >= vacancy.positions


def pending_in_order(vacancy):
    """Candidaturas pendentes por ordem de candidatura."""
    return (
        vacancy.applications.filter(status=Application.Status.PENDING)
        .select_related("worker__user")
        .order_by("created_at", "pk")
    )


def waitlist_position(application):
    """Posição (1, 2, ...) na lista de espera, ou None se a equipe não está completa."""
    if application.status != Application.Status.PENDING:
        return None
    vacancy = application.vacancy
    if not is_team_complete(vacancy):
        return None
    ahead = (
        pending_in_order(vacancy)
        .filter(created_at__lt=application.created_at)
        .count()
        + pending_in_order(vacancy)
        .filter(created_at=application.created_at, pk__lt=application.pk)
        .count()
    )
    return ahead + 1


def waitlist_label(position):
    return f"Na lista de espera (posição {position})"


def can_call_now(vacancy, now, params=None):
    """Ninguém é chamado em vaga encerrada ou a menos de `no_show_tolerance_minutes` do fim."""
    params = params or PlatformParameters.get()
    if vacancy.status not in CALLABLE_VACANCY_STATUSES:
        return False
    limit = vacancy.ends_at - timedelta(minutes=params.no_show_tolerance_minutes)
    return now < limit


def is_eligible(application, vacancy, now):
    """Aprovado, com PIX, sem suspensão e sem conflito de horário."""
    worker = application.worker
    return (
        worker.verification_status == Worker.VerificationStatus.APPROVED
        and bool(worker.pix_key)
        and not worker.is_suspended(now)
        and not applications.has_overlap(worker, vacancy)
    )


@transaction.atomic
def call_from_waitlist(vacancy, *, was_full, now=None):
    """Aprova automaticamente, na ordem, quem ocupa as posições liberadas. Idempotente.

    `was_full`: a equipe estava completa antes da liberação. Sem isso os pendentes não eram
    lista de espera (a empresa ainda estava escolhendo) e a decisão continua com a empresa.
    O bloqueio da vaga e o cálculo das posições livres evitam aprovar duas pessoas para a
    mesma posição. Devolve as alocações criadas.
    """
    now = now or timezone.now()
    if not was_full:
        return []
    vacancy = Vacancy.objects.select_for_update().select_related("company").get(pk=vacancy.pk)
    if not vacancy.auto_call_waitlist or not can_call_now(vacancy, now):
        return []
    free = vacancy.positions - vacancy.unavailable_positions
    called = []
    for application in pending_in_order(vacancy):
        if free <= 0:
            break
        if not is_eligible(application, vacancy, now):
            continue  # pulado: continua pendente
        try:
            with transaction.atomic():
                assignment = applications.approve_application(
                    application, actor=None, now=now, from_waitlist=True
                )
        except DomainError:
            continue
        called.append(assignment)
        free -= 1
    return called
