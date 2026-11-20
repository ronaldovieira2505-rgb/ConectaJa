"""US66: selo "Contratante premium" por histórico e boas avaliações."""

from datetime import timedelta
from itertools import count

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.companies import premium
from apps.core.deadlines import process_deadlines
from apps.core.models import Notification, PlatformParameters, StateTransition
from apps.core.tests.factories import (
    NOW,
    make_assignment,
    make_company,
    make_published_vacancy,
    make_worker,
)
from apps.reports.models import Report
from apps.vacancies.models import Assignment, Review

pytestmark = pytest.mark.django_db

_slot = count(1)


def paid_shift(company, rating=5):
    vacancy = make_published_vacancy(company=company, now=NOW, starts_in_hours=24 + next(_slot))
    assignment = make_assignment(vacancy=vacancy, worker=make_worker(), now=NOW)
    Assignment.objects.filter(pk=assignment.pk).update(status=Assignment.Status.PAID)
    if rating is not None:
        Review.objects.create(
            assignment=assignment,
            direction=Review.Direction.WORKER_TO_COMPANY,
            author=assignment.worker.user,
            rating=rating,
            created_at=NOW,
        )
    return assignment


def qualified_company(shifts=10, rating=5):
    company = make_company()
    for _ in range(shifts):
        paid_shift(company, rating=rating)
    return company


def premium_notes(company):
    users = [m.user for m in company.members.all()]
    return list(
        Notification.objects.filter(user__in=users, kind="PREMIUM").values_list("title", flat=True)
    )


def lost_contest(company, days_ago=5):
    assignment = paid_shift(company, rating=None)
    StateTransition.objects.create(
        entity_type="Assignment",
        entity_id=assignment.pk,
        from_state="CONTESTADA",
        to_state="APROVADA",
        reason="A favor do prestador",
        created_at=timezone.now() - timedelta(days=days_ago),
    )


def upheld_report(company, days_ago=5):
    Report.objects.create(
        reporter=make_worker().user,
        target_type="EMPRESA",
        company=company,
        reason="OUTRO",
        description="Descrição longa o bastante.",
        status="PROCEDENTE",
        decided_at=timezone.now() - timedelta(days=days_ago),
        decision="Confirmado.",
    )


# Ganhar ---------------------------------------------------------------------------------------


def test_company_meeting_all_criteria_earns_the_seal_and_members_are_notified():
    company = qualified_company()
    assert premium.recalculate(company) == "GANHOU"
    company.refresh_from_db()
    assert company.premium is True
    assert company.premium_since is not None
    assert premium_notes(company) == ["Sua empresa agora é Contratante premium"]
    assert StateTransition.objects.filter(
        entity_type="CompanyPremium", entity_id=company.pk, to_state="PREMIUM"
    ).exists()


def test_recalculation_is_idempotent():
    company = qualified_company()
    premium.recalculate(company)
    assert premium.recalculate(company) == ""
    assert premium_notes(company) == ["Sua empresa agora é Contratante premium"]
    assert StateTransition.objects.filter(entity_type="CompanyPremium").count() == 1


def test_recalculation_runs_with_processar_prazos():
    company = qualified_company()
    done = process_deadlines()
    assert done["selos_premium_concedidos"] == 1
    company.refresh_from_db()
    assert company.premium is True
    assert "selos_premium_concedidos" not in process_deadlines()


@pytest.mark.parametrize(
    ("shifts", "rating"),
    [(9, 5), (10, 4), (10, None)],
)
def test_criteria_not_met(shifts, rating):
    company = qualified_company(shifts=shifts, rating=rating)
    assert premium.recalculate(company) == ""
    company.refresh_from_db()
    assert company.premium is False


def test_average_is_the_displayed_rating():
    company = qualified_company(shifts=9, rating=5)
    paid_shift(company, rating=1)  # média 4,6
    assert premium.recalculate(company) == "GANHOU"


def test_unapproved_company_is_not_evaluated_by_processar_prazos():
    company = qualified_company()
    company.verification_status = "PENDENTE"
    company.save()
    process_deadlines()
    company.refresh_from_db()
    assert company.premium is False


# Perder -------------------------------------------------------------------------------------


def test_lost_contest_in_the_window_removes_the_seal_with_the_reason():
    company = qualified_company()
    premium.recalculate(company)
    lost_contest(company, days_ago=5)
    assert premium.recalculate(company) == "PERDEU"
    company.refresh_from_db()
    assert company.premium is False
    assert company.premium_since is None
    users = [m.user for m in company.members.all()]
    note = Notification.objects.filter(user__in=users, kind="PREMIUM").latest("pk")
    assert note.title == "Sua empresa perdeu o selo de Contratante premium"
    assert "contestação perdida" in note.message


def test_old_lost_contest_does_not_count():
    company = qualified_company()
    lost_contest(company, days_ago=100)
    assert premium.recalculate(company) == "GANHOU"


def test_upheld_report_in_the_window_removes_the_seal():
    company = qualified_company()
    premium.recalculate(company)
    upheld_report(company, days_ago=3)
    done = process_deadlines()
    assert done["selos_premium_retirados"] == 1
    company.refresh_from_db()
    assert company.premium is False


def test_old_upheld_report_does_not_count():
    company = qualified_company()
    upheld_report(company, days_ago=120)
    assert premium.recalculate(company) == "GANHOU"


def test_thresholds_are_platform_parameters():
    params = PlatformParameters.get()
    params.premium_min_paid_shifts = 3
    params.premium_min_rating = "4.0"
    params.save()
    company = qualified_company(shifts=3, rating=4)
    assert premium.recalculate(company) == "GANHOU"


# Onde o selo aparece ------------------------------------------------------------------------


def test_seal_on_search_card_vacancy_detail_and_public_page():
    company = qualified_company()
    premium.recalculate(company)
    now = timezone.now()
    vacancy = make_published_vacancy(company=company, now=now)
    client = APIClient()
    cards = client.get("/api/vacancies/").json()["results"]
    card = next(c for c in cards if c["id"] == vacancy.pk)
    assert card["company_premium"] is True
    detail = client.get(f"/api/vacancies/{vacancy.pk}/").json()
    assert detail["company"]["premium"] is True
    page = client.get(f"/api/companies/{company.pk}/public/").json()
    assert page["premium"] is True


def test_company_profile_shows_the_seal_or_what_is_missing():
    company = qualified_company(shifts=7, rating=5)
    client = APIClient()
    client.force_login(company.members.first().user)
    data = client.get("/api/companies/me/").json()["premium"]
    assert data["active"] is False
    assert data["missing"] == ["3 turnos pagos"]
    assert "Contratante premium" in data["explanation"]

    for _ in range(3):
        paid_shift(company)
    premium.recalculate(company)
    data = client.get("/api/companies/me/").json()["premium"]
    assert data["active"] is True
    assert data["missing"] == []
