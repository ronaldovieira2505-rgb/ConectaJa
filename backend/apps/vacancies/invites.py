"""Convidar de novo um prestador que já trabalhou bem com a empresa (US44).

O convite só avisa o prestador: ele se candidata normalmente e a empresa aprova como sempre.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.notifications import notify
from apps.vacancies.application_services import has_overlap
from apps.vacancies.models import Application, Assignment, Review, Vacancy, VacancyInvite
from apps.vacancies.review_services import reviewer_display_name
from apps.workers.models import Worker, WorkerDocument

MAX_INVITES = 20
PAID = Assignment.Status.PAID


class NotAPastWorker(DomainError):
    """O prestador nunca concluiu turno pago com a empresa."""


def past_workers(company):
    """Prestadores com turno pago na empresa (conta ativa), com quantos turnos e a nota dada.

    A nota é a média das avaliações que esta empresa deu a eles (US63).
    """
    return (
        Worker.objects.filter(
            user__is_active=True,
            assignments__status=PAID,
            assignments__vacancy__company=company,
        )
        .annotate(
            shifts_with_company=Count(
                "assignments",
                filter=Q(assignments__status=PAID, assignments__vacancy__company=company),
                distinct=True,
            ),
            rating_given=Avg(
                "assignments__reviews__rating",
                filter=Q(
                    assignments__vacancy__company=company,
                    assignments__reviews__direction=Review.Direction.COMPANY_TO_WORKER,
                ),
            ),
        )
        .select_related("user")
        .distinct()
    )


def vacancy_blocker(vacancy, now):
    """Motivo para não convidar ninguém para a vaga; None se dá para convidar."""
    if vacancy.status in (Vacancy.Status.FINISHED, Vacancy.Status.CANCELLED):
        return "Esta vaga está encerrada."
    if not vacancy.accepts_applications(now):
        return "Esta vaga não aceita mais candidaturas."
    if vacancy.unavailable_positions >= vacancy.positions:
        return "Esta vaga está lotada."
    return None


def worker_blocker(worker, vacancy, now):
    """Motivo para não convidar este prestador para esta vaga; None se pode."""
    if worker.is_suspended(now):
        return "Prestador suspenso."
    if Application.objects.filter(vacancy=vacancy, worker=worker).exists():
        return "Já se candidatou a esta vaga."
    if has_overlap(worker, vacancy):
        return "Tem outro turno nesse horário."
    return None


def _rating(value):
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal("0.1"), ROUND_HALF_UP))


def photo_url(worker):
    has_selfie = worker.documents.filter(kind=WorkerDocument.Kind.SELFIE).exists()
    return f"/api/company/workers/{worker.pk}/photo/" if has_selfie else None


def _ranking(item):
    rating = item["rating_given"]
    return (rating is None, -(rating or 0), -item["shifts_with_company"])


def invite_list(vacancy, now=None):
    """Lista de "Convidar prestadores" da vaga, da maior para a menor nota dada."""
    now = now or timezone.now()
    invited = set(vacancy.invites.values_list("worker_id", flat=True))
    blocked_vacancy = vacancy_blocker(vacancy, now)
    items = []
    for worker in past_workers(vacancy.company):
        items.append(
            {
                "worker_id": worker.pk,
                "name": reviewer_display_name(worker),
                "photo_url": photo_url(worker),
                "shifts_with_company": worker.shifts_with_company,
                "rating_given": _rating(worker.rating_given),
                "invited": worker.pk in invited,
                "blocker": None if worker.pk in invited else worker_blocker(worker, vacancy, now),
            }
        )
    # Maior nota primeiro; sem nota no fim; empate pelo número de turnos.
    items.sort(key=_ranking)
    return {
        "vacancy_blocker": blocked_vacancy,
        "max_invites": MAX_INVITES,
        "invites_left": max(MAX_INVITES - len(invited), 0),
        "results": items,
    }


@transaction.atomic
def invite(vacancy, worker, *, actor=None, now=None):
    """Convida e notifica. Cada prestador recebe um convite por vaga; até 20 por vaga."""
    now = now or timezone.now()
    vacancy = Vacancy.objects.select_for_update().select_related("company").get(pk=vacancy.pk)
    if not past_workers(vacancy.company).filter(pk=worker.pk).exists():
        raise NotAPastWorker("Prestador não encontrado entre quem já trabalhou com a empresa.")
    blocked = vacancy_blocker(vacancy, now)
    if blocked:
        raise DomainError(blocked)
    if vacancy.invites.filter(worker=worker).exists():
        raise DomainError("Este prestador já foi convidado para esta vaga.")
    blocked = worker_blocker(worker, vacancy, now)
    if blocked:
        raise DomainError(blocked)
    if vacancy.invites.count() >= MAX_INVITES:
        raise DomainError(f"Limite de {MAX_INVITES} convites por vaga atingido.")
    try:
        with transaction.atomic():
            created = VacancyInvite.objects.create(
                vacancy=vacancy, worker=worker, invited_by=actor, created_at=now
            )
    except IntegrityError:
        raise DomainError("Este prestador já foi convidado para esta vaga.") from None
    company = vacancy.company.trade_name or vacancy.company.legal_name
    notify(
        worker.user,
        "CONVITE_VAGA",
        f"A {company} convidou você para {vacancy.title}",
        "Veja a vaga e, se tiver interesse, candidate-se. A empresa aprova como sempre.",
        link=f"/vagas/{vacancy.pk}",
    )
    return created
