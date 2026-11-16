"""Números e avaliações que aparecem no perfil do prestador."""

from django.db.models import Avg, Count, Sum

RECENT_REVIEWS = 5


def worker_stats(worker):
    # Importados aqui: vagas e pagamentos dependem de prestadores, não o contrário.
    from apps.payments.models import LedgerEntry
    from apps.vacancies.models import Assignment, Review

    received = LedgerEntry.objects.filter(
        assignment__worker=worker, kind=LedgerEntry.Kind.WORKER_PAYOUT
    ).aggregate(total=Sum("amount_cents"))["total"]
    rating = Review.objects.filter(
        assignment__worker=worker, direction=Review.Direction.COMPANY_TO_WORKER
    ).aggregate(average=Avg("rating"), count=Count("pk"))
    return {
        "completed_shifts": worker.assignments.filter(status=Assignment.Status.PAID).count(),
        "total_received_cents": received or 0,
        "rating_average": None if rating["average"] is None else round(rating["average"], 1),
        "rating_count": rating["count"],
    }


def recent_reviews(worker):
    from apps.vacancies.models import Review

    reviews = (
        Review.objects.filter(
            assignment__worker=worker, direction=Review.Direction.COMPANY_TO_WORKER
        )
        .select_related("assignment__vacancy__company")
        .order_by("-created_at", "-pk")[:RECENT_REVIEWS]
    )
    return [
        {
            "id": review.pk,
            "rating": review.rating,
            "comment": review.comment,
            "company_name": (
                review.assignment.vacancy.company.trade_name
                or review.assignment.vacancy.company.legal_name
            ),
            "vacancy_title": review.assignment.vacancy.title,
            "created_at": review.created_at.isoformat(),
        }
        for review in reviews
    ]
