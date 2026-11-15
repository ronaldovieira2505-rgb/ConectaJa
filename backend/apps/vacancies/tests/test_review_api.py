"""US63: a empresa avalia o prestador depois de aprovar as horas."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Notification, PlatformParameters
from apps.core.tests.factories import make_company
from apps.vacancies.models import Assignment, Review
from apps.vacancies.tests.test_validation_api import (
    approve,
    awaiting_assignment,
    client_for,
    company_client,
)

pytestmark = pytest.mark.django_db


def review_url(assignment):
    return f"/api/assignments/{assignment.pk}/review/"


def approved_assignment():
    assignment = awaiting_assignment()
    assert approve(company_client(assignment.vacancy.company), assignment).status_code == 200
    assignment.refresh_from_db()
    return assignment


def post_review(assignment, **data):
    return company_client(assignment.vacancy.company).post(
        review_url(assignment), data, format="json"
    )


def test_company_reviews_paid_assignment_and_worker_is_notified():
    assignment = approved_assignment()
    assert assignment.status == "PAGA"

    response = post_review(assignment, rating=5, comment="Excelente.")

    assert response.status_code == 201
    body = response.json()
    assert body["rating"] == 5 and body["comment"] == "Excelente."
    review = Review.objects.get(assignment=assignment)
    assert review.direction == Review.Direction.COMPANY_TO_WORKER
    assert review.author == assignment.vacancy.company.members.first().user
    assert Notification.objects.filter(
        user=assignment.worker.user, kind="AVALIACAO_RECEBIDA"
    ).exists()


def test_comment_is_optional():
    assignment = approved_assignment()
    response = post_review(assignment, rating=3)
    assert response.status_code == 201
    assert response.json()["comment"] == ""


def test_can_review_approved_assignment_when_payment_is_pending():
    assignment = approved_assignment()
    Assignment.objects.filter(pk=assignment.pk).update(status="APROVADA")
    assert post_review(assignment, rating=4).status_code == 201


def test_review_cannot_be_repeated_or_edited():
    assignment = approved_assignment()
    assert post_review(assignment, rating=5).status_code == 201

    again = post_review(assignment, rating=1, comment="mudei de ideia")

    assert again.status_code == 409
    review = Review.objects.get(assignment=assignment)
    assert review.rating == 5 and review.comment == ""
    assert Review.objects.count() == 1


@pytest.mark.parametrize("rating", [0, 6, -1, "5", 4.5, None, True])
def test_invalid_rating_is_rejected(rating):
    assignment = approved_assignment()
    assert post_review(assignment, rating=rating).status_code == 400
    assert not Review.objects.exists()


def test_comment_limit_is_500_characters():
    assignment = approved_assignment()
    assert post_review(assignment, rating=5, comment="a" * 501).status_code == 400
    assert not Review.objects.exists()
    assert post_review(assignment, rating=5, comment="a" * 500).status_code == 201


def test_review_window_uses_platform_parameter():
    assignment = approved_assignment()
    assert PlatformParameters.get().review_window_days == 7
    Assignment.objects.filter(pk=assignment.pk).update(
        validated_at=timezone.now() - timedelta(days=8)
    )
    assert post_review(assignment, rating=5).status_code == 409

    PlatformParameters.objects.update(review_window_days=10)
    assert post_review(assignment, rating=5).status_code == 201


def test_review_inside_window_is_accepted():
    assignment = approved_assignment()
    Assignment.objects.filter(pk=assignment.pk).update(
        validated_at=timezone.now() - timedelta(days=6, hours=23)
    )
    assert post_review(assignment, rating=5).status_code == 201


@pytest.mark.parametrize(
    "status",
    ["FALTA", "CANCELADA_EMPRESA", "CANCELADA_PRESTADOR", "ESTORNADA", "AGUARDANDO_VALIDACAO"],
)
def test_review_not_allowed_in_other_statuses(status):
    assignment = approved_assignment()
    Assignment.objects.filter(pk=assignment.pk).update(status=status)
    assert post_review(assignment, rating=5).status_code == 409
    assert not Review.objects.exists()


def test_other_company_gets_404():
    assignment = approved_assignment()
    other = make_company()
    response = company_client(other).post(review_url(assignment), {"rating": 5}, format="json")
    assert response.status_code == 404
    assert not Review.objects.exists()


def test_worker_and_anonymous_cannot_review():
    assignment = approved_assignment()
    payload = {"rating": 5}
    assert APIClient().post(review_url(assignment), payload, format="json").status_code == 403
    worker = client_for(assignment.worker.user)
    assert worker.post(review_url(assignment), payload, format="json").status_code == 403
    assert not Review.objects.exists()


def test_not_reviewing_does_not_block_payment():
    assignment = approved_assignment()
    assert assignment.status == "PAGA"
    assert not Review.objects.exists()
