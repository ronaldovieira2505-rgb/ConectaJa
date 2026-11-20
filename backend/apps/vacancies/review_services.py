"""Avaliação do prestador pela empresa (US63). A entidade `Review` também serve à US64."""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters, StateTransition
from apps.core.notifications import notify, notify_company
from apps.vacancies.models import Assignment, Review
from apps.workers import levels

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


def worker_review(assignment):
    """Avaliação da empresa feita pelo prestador (US64), se existir."""
    return assignment.reviews.filter(direction=D.WORKER_TO_COMPANY).first()


def _can_review(assignment, direction, now, params):
    now = now or timezone.now()
    if assignment.status not in REVIEWABLE_STATUSES:
        return False
    deadline = review_deadline(assignment, params)
    if deadline is None or now > deadline:
        return False
    return not assignment.reviews.filter(direction=direction).exists()


def can_company_review(assignment, *, now=None, params=None):
    """Alocação aprovada/paga, ainda sem avaliação e dentro do prazo."""
    return _can_review(assignment, D.COMPANY_TO_WORKER, now, params)


def can_worker_review(assignment, *, now=None, params=None):
    """Mesmas regras, para o prestador avaliar a empresa (US64)."""
    return _can_review(assignment, D.WORKER_TO_COMPANY, now, params)


def reviewer_display_name(worker):
    """Nome do prestador sem sobrenome completo (padrão "Ana S."); nunca expõe o CPF.

    Conta excluída (US11) aparece como "Prestador removido".
    """
    from apps.workers.deletion import REMOVED_NAME

    if worker.full_name == REMOVED_NAME:
        return REMOVED_NAME
    parts = (worker.full_name or "").split()
    if not parts:
        return "Prestador"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0].upper()}."


def company_rating_summary(company_ids):
    """Média (1 casa decimal) e quantidade de avaliações por empresa, em uma só consulta.

    Retorna `{company_id: {"average": float, "count": int}}`; empresas sem avaliação ficam de fora.
    """
    rows = (
        Review.objects.filter(
            direction=D.WORKER_TO_COMPANY, assignment__vacancy__company_id__in=set(company_ids)
        )
        .values("assignment__vacancy__company_id")
        .annotate(avg=Avg("rating"), total=Count("pk"))
    )
    return {
        row["assignment__vacancy__company_id"]: {
            "average": float(Decimal(str(row["avg"])).quantize(Decimal("0.1"), ROUND_HALF_UP)),
            "count": row["total"],
        }
        for row in rows
    }


def company_rating(company_id):
    """Resumo de uma empresa; sem avaliações: `{"average": None, "count": 0}`."""
    return company_rating_summary([company_id]).get(company_id) or {"average": None, "count": 0}


RECENT_REVIEWS_LIMIT = 3


def worker_rating(worker):
    """Média (1 casa decimal) e quantidade das avaliações recebidas pelo prestador.

    Sem avaliações: `{"average": None, "count": 0}`.
    """
    row = Review.objects.filter(
        direction=D.COMPANY_TO_WORKER, assignment__worker=worker
    ).aggregate(avg=Avg("rating"), total=Count("pk"))
    if not row["total"]:
        return {"average": None, "count": 0}
    average = Decimal(str(row["avg"])).quantize(Decimal("0.1"), ROUND_HALF_UP)
    return {"average": float(average), "count": row["total"]}


def worker_recent_reviews(worker, limit=RECENT_REVIEWS_LIMIT):
    """Últimas avaliações do prestador: nota, comentário, data e nome fantasia de quem avaliou.

    Não traz valores pagos nem dados da vaga (título, endereço).
    """
    reviews = (
        Review.objects.filter(direction=D.COMPANY_TO_WORKER, assignment__worker=worker)
        .select_related("assignment__vacancy__company")
        .order_by("-created_at", "-pk")[:limit]
    )
    return [
        {
            "rating": review.rating,
            "comment": review.comment,
            "created_at": review.created_at.isoformat(),
            "company_name": str(review.assignment.vacancy.company),
        }
        for review in reviews
    ]


def worker_no_shows_recent(worker, *, now=None, params=None):
    """Faltas na janela `no_show_window_days` (mesma contagem da suspensão automática)."""
    now = now or timezone.now()
    params = params or PlatformParameters.get()
    since = now - timedelta(days=params.no_show_window_days)
    return StateTransition.objects.filter(
        entity_type="Assignment",
        to_state=Assignment.Status.NO_SHOW,
        created_at__gte=since,
        entity_id__in=worker.assignments.values("pk"),
    ).count()


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
    levels.recalculate(assignment.worker, reason="Nova avaliação", now=now)
    return review


@transaction.atomic
def review_company(assignment, *, author, rating, comment="", now=None):
    """Prestador avalia a empresa (US64). Mesmas regras da US63: definitiva e com prazo."""
    now = now or timezone.now()
    rating = validate_rating(rating)
    comment = validate_comment(comment)
    assignment = Assignment.objects.select_for_update().select_related(
        "vacancy__company", "worker"
    ).get(pk=assignment.pk)
    if assignment.status not in REVIEWABLE_STATUSES:
        raise DomainError("Só é possível avaliar alocações com horas aprovadas ou pagas.")
    if assignment.reviews.filter(direction=D.WORKER_TO_COMPANY).exists():
        raise DomainError("Esta alocação já foi avaliada. A avaliação não pode ser alterada.")
    deadline = review_deadline(assignment)
    if deadline is None or now > deadline:
        raise DomainError("O prazo para avaliar esta alocação terminou.")
    try:
        with transaction.atomic():
            review = Review.objects.create(
                assignment=assignment,
                direction=D.WORKER_TO_COMPANY,
                author=author,
                rating=rating,
                comment=comment,
                created_at=now,
            )
    except IntegrityError:
        raise DomainError(
            "Esta alocação já foi avaliada. A avaliação não pode ser alterada."
        ) from None
    notify_company(
        assignment.vacancy.company,
        "AVALIACAO_RECEBIDA",
        "Sua empresa recebeu uma avaliação",
        f"{reviewer_display_name(assignment.worker)} avaliou a empresa após o turno "
        f"“{assignment.vacancy.title}”: {rating} de 5 estrelas.",
        link="/empresa/avaliacoes",
    )
    return review
