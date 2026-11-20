"""O que o prestador vê de uma empresa (US15): só o necessário para decidir.

Nunca expõe CNPJ, telefone, e-mail, endereço completo nem valores financeiros.
"""

from django.utils import timezone

from apps.companies.models import Company
from apps.companies.profile_views import logo_url
from apps.vacancies.models import Assignment, Review
from apps.vacancies.review_services import company_rating, reviewer_display_name

RECENT_REVIEWS = 5


def is_public(company, now=None):
    """Só empresa aprovada e sem suspensão tem perfil público."""
    return (
        company.verification_status == Company.VerificationStatus.APPROVED
        and not company.is_suspended(now or timezone.now())
    )


def company_summary(company, now=None):
    """Bloco "Sobre a empresa" do detalhe da vaga."""
    return {
        "id": company.pk,
        "name": company.trade_name or company.legal_name,
        "logo_url": logo_url(company),
        "district": company.district,
        "city": company.city,
        "state": company.state,
        "member_since": company.created_at.isoformat(),
        "rating": company_rating(company.pk),
        "completed_shifts": Assignment.objects.filter(
            vacancy__company=company, status=Assignment.Status.PAID
        ).count(),
        "description": company.description,
        "profile_available": is_public(company, now),
    }


def recent_reviews(company, limit=RECENT_REVIEWS):
    """Últimas avaliações dos prestadores, com o autor no padrão "Ana S."."""
    reviews = (
        Review.objects.filter(
            direction=Review.Direction.WORKER_TO_COMPANY, assignment__vacancy__company=company
        )
        .select_related("assignment__worker")
        .order_by("-created_at", "-pk")[:limit]
    )
    return [
        {
            "id": review.pk,
            "rating": review.rating,
            "comment": review.comment,
            "created_at": review.created_at.isoformat(),
            "reviewer": reviewer_display_name(review.assignment.worker),
        }
        for review in reviews
    ]
