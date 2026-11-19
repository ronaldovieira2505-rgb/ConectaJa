"""US64: o prestador avalia a empresa ao fim do turno."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Notification, PlatformParameters
from apps.core.tests.factories import make_company
from apps.vacancies.models import Assignment, Review
from apps.vacancies.review_services import company_rating, reviewer_display_name
from apps.vacancies.tests.test_review_api import approved_assignment
from apps.vacancies.tests.test_validation_api import client_for, company_client

pytestmark = pytest.mark.django_db


def url(assignment):
    return f"/api/assignments/{assignment.pk}/review-company/"


def post_review(assignment, **data):
    return client_for(assignment.worker.user).post(url(assignment), data, format="json")


def test_worker_reviews_company_and_company_is_notified():
    assignment = approved_assignment()

    response = post_review(assignment, rating=5, comment="Ótima empresa.")

    assert response.status_code == 201
    review = Review.objects.get(assignment=assignment)
    assert review.direction == Review.Direction.WORKER_TO_COMPANY
    assert review.author == assignment.worker.user
    assert Notification.objects.filter(
        user=assignment.vacancy.company.members.first().user, kind="AVALIACAO_RECEBIDA"
    ).exists()


def test_comment_is_optional_and_limited_to_500():
    assignment = approved_assignment()
    assert post_review(assignment, rating=5, comment="a" * 501).status_code == 400
    assert post_review(assignment, rating=3).status_code == 201
    assert Review.objects.get(assignment=assignment).comment == ""


@pytest.mark.parametrize("rating", [0, 6, "5", 4.5, None, True])
def test_invalid_rating_is_rejected(rating):
    assignment = approved_assignment()
    assert post_review(assignment, rating=rating).status_code == 400
    assert not Review.objects.exists()


def test_cannot_repeat_or_edit():
    assignment = approved_assignment()
    assert post_review(assignment, rating=5).status_code == 201
    assert post_review(assignment, rating=1, comment="mudei").status_code == 409
    assert Review.objects.get(assignment=assignment).rating == 5


def test_company_and_worker_reviews_are_independent():
    assignment = approved_assignment()
    company = company_client(assignment.vacancy.company)
    assert company.post(
        f"/api/assignments/{assignment.pk}/review/", {"rating": 4}, format="json"
    ).status_code == 201
    assert post_review(assignment, rating=5).status_code == 201
    assert Review.objects.count() == 2


def test_window_uses_platform_parameter():
    assignment = approved_assignment()
    Assignment.objects.filter(pk=assignment.pk).update(
        validated_at=timezone.now() - timedelta(days=8)
    )
    assert post_review(assignment, rating=5).status_code == 409
    PlatformParameters.objects.update(review_window_days=10)
    assert post_review(assignment, rating=5).status_code == 201


@pytest.mark.parametrize(
    "status",
    ["FALTA", "CANCELADA_EMPRESA", "CANCELADA_PRESTADOR", "ESTORNADA", "AGUARDANDO_VALIDACAO"],
)
def test_not_allowed_in_other_statuses(status):
    assignment = approved_assignment()
    Assignment.objects.filter(pk=assignment.pk).update(status=status)
    assert post_review(assignment, rating=5).status_code == 409
    assert not Review.objects.exists()


def test_approved_assignment_can_be_reviewed():
    assignment = approved_assignment()
    Assignment.objects.filter(pk=assignment.pk).update(status="APROVADA")
    assert post_review(assignment, rating=4).status_code == 201


def test_other_worker_company_and_anonymous_are_blocked():
    assignment = approved_assignment()
    other = approved_assignment()
    assert (
        client_for(other.worker.user).post(url(assignment), {"rating": 5}, format="json")
    ).status_code == 404
    assert company_client(assignment.vacancy.company).post(
        url(assignment), {"rating": 5}, format="json"
    ).status_code == 403
    assert APIClient().post(url(assignment), {"rating": 5}, format="json").status_code == 403
    assert not Review.objects.exists()


def test_jobs_expose_review_button_state():
    assignment = approved_assignment()
    client = client_for(assignment.worker.user)

    def job():
        groups = client.get("/api/workers/me/jobs/").json()["groups"]
        return next(i for g in groups.values() for i in g if i["id"] == assignment.pk)

    assert job()["can_review"] is True and job()["review_deadline"]
    post_review(assignment, rating=4, comment="Bom")
    after = job()
    assert after["can_review"] is False
    assert after["my_review"] == {"rating": 4, "comment": "Bom"}


def test_rating_average_and_count_in_search_and_detail():
    assignment = approved_assignment()
    other = approved_assignment()
    company = assignment.vacancy.company
    Assignment.objects.filter(pk=other.pk).update(vacancy=assignment.vacancy)
    assert post_review(assignment, rating=5).status_code == 201
    other.refresh_from_db()
    assert post_review(other, rating=4).status_code == 201
    assert company_rating(company.pk) == {"average": 4.5, "count": 2}


def test_no_reviews_shows_empty_summary():
    assert company_rating(make_company().pk) == {"average": None, "count": 0}


def test_rating_rounds_to_one_decimal():
    assignments = [approved_assignment() for _ in range(3)]
    company = assignments[0].vacancy.company
    for a, value in zip(assignments, (5, 5, 4), strict=True):
        Assignment.objects.filter(pk=a.pk).update(vacancy=assignments[0].vacancy)
        a.refresh_from_db()
        assert post_review(a, rating=value).status_code == 201
    assert company_rating(company.pk) == {"average": 4.7, "count": 3}


def test_company_sees_reviews_with_masked_worker_name():
    assignment = approved_assignment()
    worker = assignment.worker
    worker.full_name = "Ana Maria Souza Silva"
    worker.save()
    post_review(assignment, rating=5, comment="Pagamento rápido.")

    body = company_client(assignment.vacancy.company).get("/api/company/reviews/").json()

    assert body["summary"] == {"average": 5.0, "count": 1}
    item = body["results"][0]
    assert item["reviewer"] == "Ana S."
    assert item["comment"] == "Pagamento rápido."
    assert worker.cpf not in str(body) and "Maria" not in str(body)


def test_reviewer_display_name_variants():
    class W:
        full_name = ""

    assert reviewer_display_name(W) == "Prestador"
    W.full_name = "ana"
    assert reviewer_display_name(W) == "ana"
    W.full_name = "ana souza"
    assert reviewer_display_name(W) == "ana S."


def test_other_company_does_not_see_reviews():
    assignment = approved_assignment()
    post_review(assignment, rating=5)
    body = company_client(make_company()).get("/api/company/reviews/").json()
    assert body["results"] == []


def test_search_card_and_detail_show_company_rating():
    from apps.core.tests.factories import make_published_vacancy

    vacancy = make_published_vacancy(now=timezone.now(), positions=2)
    paid = approved_assignment()
    Assignment.objects.filter(pk=paid.pk).update(vacancy=vacancy)
    paid.refresh_from_db()
    assert post_review(paid, rating=5).status_code == 201

    cards = APIClient().get("/api/vacancies/").json()["results"]
    card = next(c for c in cards if c["id"] == vacancy.pk)
    assert card["company_rating"] == {"average": 5.0, "count": 1}
    detail = APIClient().get(f"/api/vacancies/{vacancy.pk}/").json()
    assert detail["company_rating"] == {"average": 5.0, "count": 1}


def test_search_card_without_reviews_has_empty_rating():
    from apps.core.tests.factories import make_published_vacancy

    vacancy = make_published_vacancy(now=timezone.now())
    [card] = APIClient().get("/api/vacancies/").json()["results"]
    assert card["id"] == vacancy.pk
    assert card["company_rating"] == {"average": None, "count": 0}
    detail = APIClient().get(f"/api/vacancies/{vacancy.pk}/").json()
    assert detail["company_rating"] == {"average": None, "count": 0}
