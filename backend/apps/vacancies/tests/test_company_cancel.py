"""US71: a empresa cancela turno ou vaga inteira com antecedência e recebe o valor de volta."""

from datetime import timedelta

import pytest
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Notification, PlatformParameters, StateTransition
from apps.core.tests.factories import (
    make_assignment,
    make_company,
    make_published_vacancy,
    make_worker,
)
from apps.vacancies import application_services as applications
from apps.vacancies import search
from apps.vacancies.models import Application, Assignment, Vacancy

pytestmark = pytest.mark.django_db

REASON = {"reason": "Mudança de planos"}


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def company_client(company):
    return client_for(company.members.first().user)


def cancel_url(assignment):
    return f"/api/assignments/{assignment.pk}/cancel-by-company/"


def entries(custody):
    return {
        row["kind"]: row["total"]
        for row in custody.entries.values("kind").annotate(total=Sum("amount_cents"))
    }


def assert_invariant(custody):
    totals = entries(custody)
    kinds = ("REPASSE_PRESTADOR", "TAXA_PLATAFORMA", "ESTORNO_CONTRATANTE")
    used = sum(totals.get(kind, 0) for kind in kinds)
    assert totals["RETENCAO"] == used


def near_start(assignment, minutes):
    vacancy = assignment.vacancy
    vacancy.starts_at = timezone.now() + timedelta(minutes=minutes)
    vacancy.ends_at = vacancy.starts_at + timedelta(hours=4)
    vacancy.save()


def real_assignment(positions=1, **kw):
    """Alocação CONFIRMADA em vaga que começa daqui a 48 h (relógio real)."""
    now = timezone.now()
    vacancy = make_published_vacancy(now=now, starts_in_hours=48, positions=positions, **kw)
    return make_assignment(vacancy=vacancy, now=now)


def test_cancel_assignment_refunds_notifies_and_audits():
    assignment = real_assignment()
    company = assignment.vacancy.company

    response = company_client(company).post(cancel_url(assignment), REASON, format="json")

    assert response.status_code == 200
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CANCELLED_BY_COMPANY
    custody = assignment.vacancy.custody
    assert entries(custody)["ESTORNO_CONTRATANTE"] == 10000
    assert_invariant(custody)
    assert Notification.objects.filter(
        user=assignment.worker.user, kind="TURNO_CANCELADO"
    ).exists()
    transition = StateTransition.objects.get(
        entity_type="Assignment", entity_id=assignment.pk, to_state="CANCELADA_EMPRESA"
    )
    assert transition.reason == "Mudança de planos"
    assert transition.from_state == "CONFIRMADA"
    assert transition.actor == company.members.first().user


def test_cancel_inside_free_window_is_blocked_and_nothing_changes():
    assignment = real_assignment()
    near_start(assignment, minutes=23 * 60)

    response = company_client(assignment.vacancy.company).post(
        cancel_url(assignment), REASON, format="json"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Cancelamentos só podem ser feitos até 24 h antes do início. Fale com o suporte."
    )
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED
    assert "ESTORNO_CONTRATANTE" not in entries(assignment.vacancy.custody)
    assert not Notification.objects.filter(kind="TURNO_CANCELADO").exists()


def test_cancel_exactly_at_the_limit_is_allowed():
    assignment = real_assignment()
    near_start(assignment, minutes=24 * 60 + 1)

    response = company_client(assignment.vacancy.company).post(
        cancel_url(assignment), REASON, format="json"
    )

    assert response.status_code == 200


def test_cancel_window_comes_from_platform_parameters():
    assignment = real_assignment()
    near_start(assignment, minutes=23 * 60)
    PlatformParameters.objects.update(free_cancel_minutes_before=600)

    response = company_client(assignment.vacancy.company).post(
        cancel_url(assignment), REASON, format="json"
    )

    assert response.status_code == 200


@pytest.mark.parametrize("payload", [{}, {"reason": ""}, {"reason": "   "}])
def test_reason_is_required_and_nothing_is_saved(payload):
    assignment = real_assignment()

    response = company_client(assignment.vacancy.company).post(
        cancel_url(assignment), payload, format="json"
    )

    assert response.status_code == 400
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED
    assert "ESTORNO_CONTRATANTE" not in entries(assignment.vacancy.custody)
    assert not StateTransition.objects.filter(to_state="CANCELADA_EMPRESA").exists()


def test_only_the_owner_company_can_cancel():
    assignment = real_assignment()
    other = company_client(make_company())
    worker_client = client_for(assignment.worker.user)

    assert other.post(cancel_url(assignment), REASON, format="json").status_code == 404
    assert worker_client.post(cancel_url(assignment), REASON, format="json").status_code == 403
    assert APIClient().post(cancel_url(assignment), REASON, format="json").status_code in (401, 403)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED


def test_cancelled_position_does_not_return_to_search_or_accept_new_approvals():
    now = timezone.now()
    vacancy = make_published_vacancy(now=now, starts_in_hours=48, positions=1)
    waiting = applications.apply_to_vacancy(vacancy, make_worker(), now=now)
    assignment = make_assignment(vacancy=vacancy, now=now)
    company_client(vacancy.company).post(cancel_url(assignment), REASON, format="json")

    assert vacancy.pk not in [v.pk for v in search.searchable_vacancies(now)]
    waiting.refresh_from_db()
    with pytest.raises(Exception, match="posição livre"):
        applications.approve_application(waiting, now=now)
    with pytest.raises(Exception, match="lotada"):
        applications.apply_to_vacancy(vacancy, make_worker(), now=now)
    assert vacancy.filled_positions == 0


def test_cancel_one_of_two_keeps_other_assignment_and_vacancy_published():
    now = timezone.now()
    vacancy = make_published_vacancy(now=now, starts_in_hours=48, positions=2)
    first = make_assignment(vacancy=vacancy, now=now)
    second = make_assignment(vacancy=vacancy, now=now)

    company_client(vacancy.company).post(cancel_url(first), REASON, format="json")

    first.refresh_from_db()
    second.refresh_from_db()
    vacancy.refresh_from_db()
    assert first.status == Assignment.Status.CANCELLED_BY_COMPANY
    assert second.status == Assignment.Status.CONFIRMED
    assert vacancy.status == Vacancy.Status.PUBLISHED
    assert entries(vacancy.custody)["ESTORNO_CONTRATANTE"] == 10000
    # A custódia segue retida com o valor da posição que continua ativa.
    assert entries(vacancy.custody)["RETENCAO"] - 10000 == 10000


def test_cannot_cancel_twice_or_after_check_in():
    assignment = real_assignment()
    client = company_client(assignment.vacancy.company)
    assert client.post(cancel_url(assignment), REASON, format="json").status_code == 200

    again = client.post(cancel_url(assignment), REASON, format="json")

    assert again.status_code == 409
    assert Assignment.objects.get(pk=assignment.pk).status == "CANCELADA_EMPRESA"
    assert entries(assignment.vacancy.custody)["ESTORNO_CONTRATANTE"] == 10000


# --- vaga inteira -----------------------------------------------------------------------


def vacancy_with_team(positions=2, hired=2):
    now = timezone.now()
    vacancy = make_published_vacancy(now=now, starts_in_hours=48, positions=positions)
    team = [make_assignment(vacancy=vacancy, now=now) for _ in range(hired)]
    pending = None
    if hired < positions:
        pending = applications.apply_to_vacancy(vacancy, make_worker(), now=now)
    return vacancy, team, pending


def cancel_vacancy(vacancy, payload=REASON):
    return company_client(vacancy.company).post(
        f"/api/vacancies/{vacancy.pk}/cancel/", payload, format="json"
    )


def test_cancel_whole_vacancy_refunds_everything_and_notifies_everyone():
    vacancy, team, _ = vacancy_with_team(positions=3, hired=2)
    pending = applications.apply_to_vacancy(vacancy, make_worker(), now=timezone.now())

    response = cancel_vacancy(vacancy)

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELADA"
    vacancy.refresh_from_db()
    assert vacancy.status == Vacancy.Status.CANCELLED
    for assignment in team:
        assignment.refresh_from_db()
        assert assignment.status == Assignment.Status.CANCELLED_BY_COMPANY
        assert Notification.objects.filter(
            user=assignment.worker.user, kind="TURNO_CANCELADO"
        ).exists()
    pending.refresh_from_db()
    assert pending.status == Application.Status.EXPIRED
    assert Notification.objects.filter(
        user=pending.worker.user, kind="CANDIDATURA_EXPIRADA"
    ).exists()
    custody = vacancy.custody
    custody.refresh_from_db()
    assert custody.status == "ENCERRADA"
    totals = entries(custody)
    assert totals["RETENCAO"] == 30000
    assert totals["ESTORNO_CONTRATANTE"] == 30000
    assert_invariant(custody)
    reasons = StateTransition.objects.filter(
        entity_type="Vacancy", entity_id=vacancy.pk, to_state="CANCELADA"
    ).values_list("reason", flat=True)
    assert list(reasons) == ["Mudança de planos"]


def test_cancel_vacancy_with_closed_applications_status():
    vacancy, team, _ = vacancy_with_team(positions=1, hired=1)
    Vacancy.objects.filter(pk=vacancy.pk).update(status=Vacancy.Status.APPLICATIONS_CLOSED)

    response = cancel_vacancy(vacancy)

    assert response.status_code == 200
    assert Vacancy.objects.get(pk=vacancy.pk).status == Vacancy.Status.CANCELLED


def test_cancel_whole_vacancy_inside_free_window_is_blocked():
    vacancy, team, _ = vacancy_with_team(positions=1, hired=1)
    near_start(team[0], minutes=60)

    response = cancel_vacancy(vacancy)

    assert response.status_code == 409
    assert "Fale com o suporte" in response.json()["detail"]
    assert Vacancy.objects.get(pk=vacancy.pk).status == Vacancy.Status.PUBLISHED
    team[0].refresh_from_db()
    assert team[0].status == Assignment.Status.CONFIRMED
    assert "ESTORNO_CONTRATANTE" not in entries(vacancy.custody)


@pytest.mark.parametrize("payload", [{}, {"reason": " "}])
def test_cancel_whole_vacancy_requires_reason(payload):
    vacancy, team, _ = vacancy_with_team(positions=1, hired=1)

    response = cancel_vacancy(vacancy, payload)

    assert response.status_code == 400
    assert Vacancy.objects.get(pk=vacancy.pk).status == Vacancy.Status.PUBLISHED
    team[0].refresh_from_db()
    assert team[0].status == Assignment.Status.CONFIRMED


def test_cancel_whole_vacancy_only_by_owner():
    vacancy, _team, _ = vacancy_with_team(positions=1, hired=1)

    other = company_client(make_company()).post(
        f"/api/vacancies/{vacancy.pk}/cancel/", REASON, format="json"
    )
    worker = client_for(make_worker().user).post(
        f"/api/vacancies/{vacancy.pk}/cancel/", REASON, format="json"
    )

    assert other.status_code == 404
    assert worker.status_code == 403
    assert Vacancy.objects.get(pk=vacancy.pk).status == Vacancy.Status.PUBLISHED


def test_vacancy_without_approved_keeps_remove_flow():
    now = timezone.now()
    vacancy = make_published_vacancy(now=now, starts_in_hours=48)
    client = company_client(vacancy.company)

    refused = cancel_vacancy(vacancy)
    removed = client.post(f"/api/vacancies/{vacancy.pk}/remove/")

    assert refused.status_code == 409
    assert "Remover anúncio" in refused.json()["detail"]
    assert removed.status_code == 200
    assert removed.json()["status"] == "CANCELADA"
    assert entries(vacancy.custody)["ESTORNO_CONTRATANTE"] == 10000
    assert_invariant(vacancy.custody)


def test_candidates_endpoint_exposes_cancel_window_and_team_status():
    vacancy, team, _ = vacancy_with_team(positions=1, hired=1)
    PlatformParameters.objects.update(free_cancel_minutes_before=1440)

    data = company_client(vacancy.company).get(f"/api/vacancies/{vacancy.pk}/candidates/").json()

    assert data["free_cancel_minutes_before"] == 1440
    assert data["team"][0]["id"] == team[0].pk
    assert data["team"][0]["status"] == "CONFIRMADA"
