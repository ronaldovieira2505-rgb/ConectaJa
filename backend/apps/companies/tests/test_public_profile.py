"""US15 — descrição e página pública da empresa para o prestador."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.companies.models import Company
from apps.core.tests.factories import (
    LAT,
    LNG,
    make_assignment,
    make_company,
    make_published_vacancy,
    make_worker,
)
from apps.vacancies import assignment_services as assignments
from apps.vacancies.models import Review

pytestmark = pytest.mark.django_db

SUMMARY_FIELDS = {
    "id",
    "name",
    "logo_url",
    "district",
    "city",
    "state",
    "member_since",
    "rating",
    "completed_shifts",
    "description",
    "profile_available",
}


def public_url(company):
    return f"/api/companies/{company.pk}/public/"


def full_company(**kw):
    company = make_company()
    fields = {
        "trade_name": "Mercado Bom",
        "phone": "11999998888",
        "street": "Rua Secreta",
        "number": "42",
        "zip_code": "01001000",
        "district": "Centro",
        "city": "São Paulo",
        "state": "SP",
        "description": "Supermercado de bairro.",
    }
    fields.update(kw)
    Company.objects.filter(pk=company.pk).update(**fields)
    company.refresh_from_db()
    return company


def review(company, rating, comment="", full_name="Ana Paula Ribeiro", days_ago=0, **kw):
    vacancy = make_published_vacancy(company=company, **kw)
    worker = make_worker()
    worker.full_name = full_name
    worker.save(update_fields=["full_name"])
    assignment = make_assignment(vacancy=vacancy, worker=worker)
    return Review.objects.create(
        assignment=assignment,
        direction=Review.Direction.WORKER_TO_COMPANY,
        author=worker.user,
        rating=rating,
        comment=comment,
        created_at=timezone.now() - timedelta(days=days_ago),
    )


def test_public_page_shows_only_what_the_worker_needs():
    company = full_company()

    response = APIClient().get(public_url(company))

    assert response.status_code == 200
    data = response.json()
    assert set(data) == SUMMARY_FIELDS | {"open_vacancies", "recent_reviews"}
    assert data["name"] == "Mercado Bom"
    assert (data["district"], data["city"], data["state"]) == ("Centro", "São Paulo", "SP")
    assert data["description"] == "Supermercado de bairro."
    assert data["member_since"] == company.created_at.isoformat()
    text = response.content.decode()
    for secret in (company.cnpj, "11999998888", "Rua Secreta", "01001000", company.legal_name):
        assert secret not in text
    assert "@" not in text  # nenhum e-mail


def test_public_page_lists_open_vacancies_of_the_company_only():
    company = full_company()
    now = timezone.now()
    mine = make_published_vacancy(company=company, now=now, title="Reposição de estoque")
    make_published_vacancy(company=make_company(), now=now, title="Vaga de outra empresa")

    data = APIClient().get(public_url(company)).json()

    assert [v["id"] for v in data["open_vacancies"]] == [mine.pk]
    assert data["open_vacancies"][0]["net_cents"] == 9700


def test_rating_and_the_five_most_recent_reviews_with_short_name():
    company = full_company()
    for i in range(6):
        review(company, 4 + i % 2, f"Comentário {i}", days_ago=i, starts_in_hours=48 + i)

    data = APIClient().get(public_url(company)).json()

    assert data["rating"] == {"average": 4.5, "count": 6}
    reviews = data["recent_reviews"]
    assert [r["comment"] for r in reviews] == [f"Comentário {i}" for i in range(5)]
    assert reviews[0]["reviewer"] == "Ana R."
    assert set(reviews[0]) == {"id", "rating", "comment", "created_at", "reviewer"}


def test_completed_shifts_count_only_paid_assignments():
    company = full_company()
    assignment = make_assignment(vacancy=make_published_vacancy(company=company))
    start = assignment.vacancy.starts_at
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)
    assignments.check_out(assignment, now=start + timedelta(hours=4))
    assignments.approve_hours(assignment, now=start + timedelta(hours=5))
    assignments.settle(assignment, now=start + timedelta(hours=6))
    make_assignment(vacancy=make_published_vacancy(company=company, starts_in_hours=72))

    data = APIClient().get(public_url(company)).json()

    assert data["completed_shifts"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"verification_status": Company.VerificationStatus.PENDING},
        {"verification_status": Company.VerificationStatus.REJECTED},
        {"suspension_indefinite": True},
    ],
)
def test_pending_rejected_or_suspended_company_has_no_public_page(change):
    company = full_company(**change)

    response = APIClient().get(public_url(company))

    assert response.status_code == 404


def test_unknown_company_returns_404():
    assert APIClient().get("/api/companies/999999/public/").status_code == 404


def test_vacancy_detail_has_the_about_the_company_block():
    company = full_company()
    vacancy = make_published_vacancy(company=company)

    data = APIClient().get(f"/api/vacancies/{vacancy.pk}/").json()

    block = data["company"]
    assert set(block) == SUMMARY_FIELDS
    assert block["id"] == company.pk
    assert block["name"] == "Mercado Bom"
    assert block["description"] == "Supermercado de bairro."
    assert block["profile_available"] is True
    assert company.cnpj not in str(block)


def test_vacancy_detail_of_suspended_company_hides_profile_link():
    company = full_company()
    vacancy = make_published_vacancy(company=company)
    Company.objects.filter(pk=company.pk).update(suspension_indefinite=True)

    block = APIClient().get(f"/api/vacancies/{vacancy.pk}/").json()["company"]

    assert block["profile_available"] is False
