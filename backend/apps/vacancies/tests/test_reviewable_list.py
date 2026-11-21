"""US63 na tela: turnos que a empresa ainda pode avaliar aparecem em "Confirmar presença".

A API de avaliação já existia, mas nenhuma tela a usava: depois de aprovar as horas o turno
sumia da lista e a empresa não tinha onde avaliar o prestador.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import PlatformParameters
from apps.core.tests.factories import make_assignment, make_company
from apps.vacancies import review_services
from apps.vacancies.models import Assignment

pytestmark = pytest.mark.django_db

URL = "/api/company/assignments/pending/"


def approved(status=Assignment.Status.APPROVED, validated_days_ago=1):
    assignment = make_assignment(now=timezone.now(), starts_in_hours=48)
    Assignment.objects.filter(pk=assignment.pk).update(
        status=status, validated_at=timezone.now() - timedelta(days=validated_days_ago)
    )
    return Assignment.objects.get(pk=assignment.pk)


def to_review(company, **params):
    client = APIClient()
    client.force_login(company.members.first().user)
    return client.get(URL, params).json()["to_review"]


def test_approved_and_paid_shifts_are_listed_with_the_deadline():
    first = approved()
    company = first.vacancy.company
    [item] = to_review(company)
    assert item["id"] == first.pk
    assert item["worker_first_name"] == "Prestador"
    assert item["status"] == "APROVADA"
    deadline = first.validated_at + timedelta(days=PlatformParameters.get().review_window_days)
    assert item["review_deadline"] == deadline.isoformat()

    paid = approved(status=Assignment.Status.PAID)
    assert [i["id"] for i in to_review(paid.vacancy.company)] == [paid.pk]


def test_reviewed_expired_and_other_statuses_are_not_listed():
    reviewed = approved()
    review_services.review_worker(
        reviewed, author=reviewed.vacancy.company.members.first().user, rating=5
    )
    assert to_review(reviewed.vacancy.company) == []

    expired = approved(validated_days_ago=8)
    assert to_review(expired.vacancy.company) == []

    for status in (Assignment.Status.NO_SHOW, Assignment.Status.REFUNDED):
        other = approved(status=status)
        assert to_review(other.vacancy.company) == []


def test_only_the_owner_company_sees_them_and_the_vacancy_filter_works():
    item = approved()
    assert to_review(make_company()) == []
    company = item.vacancy.company
    assert [i["id"] for i in to_review(company, vacancy=item.vacancy_id)] == [item.pk]
    assert to_review(company, vacancy=item.vacancy_id + 999) == []
