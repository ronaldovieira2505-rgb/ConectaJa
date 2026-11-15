"""Avaliação do prestador pela empresa (US63). A entidade `Review` também serve à US64."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.core.notifications import notify
from apps.vacancies.models import Assignment, Review

S = Assignment.Status
D = Review.Direction

REVIEWABLE_STATUSES = (S.APPROVED, S.PAID)


def review_deadline(assignment, params=None):
    """Fim do prazo (`review_window_days` após a aprovação das horas)."""
    if assignment.validated_at is None:
        return None
    params = params or PlatformParameters.get()
    return assignment.validated_at + timedelta(days=params.review_window_days)


def company_review(assignment):
    return assignment.reviews.filter(direction=D.COMPANY_TO_WORKER).first()


def can_company_review(assignment, *, now=None, params=None):
    """Alocação aprovada/paga, ainda sem avaliação e dentro do prazo."""
    now = now or timezone.now()
    if assignment.status not in REVIEWABLE_STATUSES:
        return False
    deadline = review_deadline(assignment, params)
    if deadline is None or now > deadline:
        return False
    return not assignment.reviews.filter(direction=D.COMPANY_TO_WORKER).exists()


def validate_rating(rating):
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
        raise DomainError("A nota deve ser um número inteiro de 1 a 5.")
    return rating


def validate_comment(comment):
    if comment is None:
        return ""
    if not isinstance(comment, str):
        raise DomainError("Comentário inválido.")
    comment = comment.strip()
    if len(comment) > Review.COMMENT_MAX_LENGTH:
        raise DomainError(
            f"O comentário pode ter no máximo {Review.COMMENT_MAX_LENGTH} caracteres."
        )
    return comment


@transaction.atomic
def review_worker(assignment, *, author, rating, comment="", now=None):
    """Empresa avalia o prestador. Definitiva: não há nova avaliação nem edição."""
    now = now or timezone.now()
    rating = validate_rating(rating)
    comment = validate_comment(comment)
    # Trava a alocação para que duas requisições simultâneas não avaliem duas vezes.
    assignment = Assignment.objects.select_for_update().select_related(
        "vacancy", "worker__user"
    ).get(pk=assignment.pk)
    if assignment.status not in REVIEWABLE_STATUSES:
        raise DomainError("Só é possível avaliar alocações com horas aprovadas ou pagas.")
    if assignment.reviews.filter(direction=D.COMPANY_TO_WORKER).exists():
        raise DomainError("Esta alocação já foi avaliada. A avaliação não pode ser alterada.")
    deadline = review_deadline(assignment)
    if deadline is None or now > deadline:
        raise DomainError("O prazo para avaliar esta alocação terminou.")
    try:
        with transaction.atomic():
            review = Review.objects.create(
                assignment=assignment,
                direction=D.COMPANY_TO_WORKER,
                author=author,
                rating=rating,
                comment=comment,
                created_at=now,
            )
    except IntegrityError:
        raise DomainError(
            "Esta alocação já foi avaliada. A avaliação não pode ser alterada."
        ) from None
    notify(
        assignment.worker.user,
        "AVALIACAO_RECEBIDA",
        "Você recebeu uma avaliação",
        f"A empresa avaliou o seu trabalho em “{assignment.vacancy.title}”: "
        f"{rating} de 5 estrelas.",
        link="/meus-trabalhos",
    )
    return review
