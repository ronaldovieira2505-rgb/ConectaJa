"""Vagas favoritas do prestador (US18)."""

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.models import PlatformParameters
from apps.vacancies import search
from apps.vacancies.models import Assignment, FavoriteVacancy, Vacancy
from apps.vacancies.review_services import company_rating_summary

V = Vacancy.Status

# Só vagas que já apareceram na busca podem ser favoritadas.
FAVORITABLE_STATUSES = (V.PUBLISHED, V.APPLICATIONS_CLOSED, V.IN_PROGRESS)
FINAL_STATUSES = (V.FINISHED, V.CANCELLED)
CLOSED = "Encerrada"
FULL = "Lotada"


def favorite_ids(user):
    """Ids das vagas favoritas do usuário; vazio para visitante, empresa ou admin."""
    if not (user and user.is_authenticated and user.role == Role.WORKER):
        return set()
    return set(
        FavoriteVacancy.objects.filter(worker__user=user).values_list("vacancy_id", flat=True)
    )


def add_favorite(worker, vacancy):
    """Salva nos favoritos. Repetir não duplica. Devolve se criou agora."""
    try:
        with transaction.atomic():
            _, created = FavoriteVacancy.objects.get_or_create(worker=worker, vacancy=vacancy)
    except IntegrityError:  # dois cliques simultâneos
        return False
    return created


def remove_favorite(worker, vacancy_id):
    FavoriteVacancy.objects.filter(worker=worker, vacancy_id=vacancy_id).delete()


def closed_label(vacancy, now):
    """"Encerrada" (terminou, cancelou ou fechou candidaturas), "Lotada" ou None."""
    if vacancy.status in FINAL_STATUSES or not vacancy.accepts_applications(now):
        return CLOSED
    if vacancy.filled >= vacancy.positions:
        return FULL
    return None


def favorites_payload(worker, now=None):
    """Favoritas com o mesmo card da busca, da que começa antes para a que começa depois."""
    now = now or timezone.now()
    ids = set(
        FavoriteVacancy.objects.filter(worker=worker).values_list("vacancy_id", flat=True)
    )
    vacancies = (
        Vacancy.objects.filter(pk__in=ids)
        .select_related("company", "custody")
        .annotate(
            filled=Count(
                "assignments", filter=Q(assignments__status__in=Assignment.UNAVAILABLE_STATUSES)
            )
        )
        .order_by("starts_at", "pk")
    )
    params = PlatformParameters.get()
    ratings = company_rating_summary({v.company_id for v in vacancies})
    items = []
    for vacancy in vacancies:
        card = search.serialize_card(vacancy, None, params, ratings, favorites=ids)
        card["closed_label"] = closed_label(vacancy, now)
        items.append(card)
    return items
