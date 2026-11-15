"""US57: empresa contesta as horas; admin decide a contestação."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.deadlines import process_deadlines
from apps.core.models import Notification, PlatformParameters, StateTransition
from apps.core.tests.factories import make_admin, make_company, make_worker
from apps.vacancies.models import Assignment
from apps.vacancies.tests.test_validation_api import (
    awaiting_assignment,
    client_for,
    company_client,
    entries,
)

pytestmark = pytest.mark.django_db

REASON = "O prestador saiu duas horas antes."


def contest(client, assignment, reason=REASON):
    return client.post(
        f"/api/assignments/{assignment.pk}/contest/", {"reason": reason}, format="json"
    )


def admin_client():
    client = Client()
    client.force_login(make_admin())
    return client


def resolve_url(assignment):
    return f"/admin/vacancies/assignment/{assignment.pk}/resolver-contestacao/"


def contested_assignment():
    assignment = awaiting_assignment()
    assert contest(company_client(assignment.vacancy.company), assignment).status_code == 200
    assignment.refresh_from_db()
    return assignment


def test_company_contests_within_window_and_notifies_worker_and_admins():
    assignment = awaiting_assignment()
    admin = make_admin()

    response = contest(company_client(assignment.vacancy.company), assignment)

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "CONTESTADA"
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONTESTED
    transition = StateTransition.objects.get(
        entity_type="Assignment", entity_id=assignment.pk, to_state="CONTESTADA"
    )
    assert transition.reason == REASON
    assert Notification.objects.filter(user=assignment.worker.user, kind="CONTESTACAO").exists()
    assert Notification.objects.filter(user=admin, kind="CONTESTACAO").exists()


def test_contested_assignment_is_not_auto_approved():
    assignment = contested_assignment()
    window = PlatformParameters.get().contest_window_minutes

    done = process_deadlines(assignment.check_out_at + timedelta(minutes=window + 10))

    assert "aprovacoes_automaticas" not in done
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONTESTED


def test_empty_reason_is_rejected_and_nothing_changes():
    assignment = awaiting_assignment()
    client = company_client(assignment.vacancy.company)

    for reason in ("", "   "):
        response = contest(client, assignment, reason)
        assert response.status_code == 400
        assert response.json()["detail"] == "Informe o motivo da contestação."
    assert contest(client, assignment, None).status_code == 400
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.AWAITING_VALIDATION
    assert not Notification.objects.filter(kind="CONTESTACAO").exists()


def test_contest_after_window_is_rejected_even_before_auto_approval_runs():
    assignment = awaiting_assignment()
    PlatformParameters.objects.update(contest_window_minutes=10)
    assignment.check_out_at = timezone.now() - timedelta(minutes=11)
    assignment.save()

    response = contest(company_client(assignment.vacancy.company), assignment)

    assert response.status_code == 409
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.AWAITING_VALIDATION


def test_contest_after_auto_approval_is_rejected():
    assignment = awaiting_assignment()
    window = PlatformParameters.get().contest_window_minutes
    process_deadlines(assignment.check_out_at + timedelta(minutes=window + 1))

    response = contest(company_client(assignment.vacancy.company), assignment)

    assert response.status_code == 409
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.PAID


def test_pending_list_hides_contest_when_window_is_over():
    assignment = awaiting_assignment()
    client = company_client(assignment.vacancy.company)
    url = "/api/company/assignments/pending/"
    assert client.get(url).json()["results"][0]["can_contest"] is True

    PlatformParameters.objects.update(contest_window_minutes=1)
    assignment.check_out_at = timezone.now() - timedelta(minutes=5)
    assignment.save()

    assert client.get(url).json()["results"][0]["can_contest"] is False


def test_contest_twice_is_rejected():
    assignment = contested_assignment()
    response = contest(company_client(assignment.vacancy.company), assignment)
    assert response.status_code == 409


def test_only_the_owner_company_contests():
    assignment = awaiting_assignment()
    assert contest(company_client(make_company()), assignment).status_code == 404
    assert contest(client_for(assignment.worker.user), assignment).status_code == 403
    assert contest(client_for(make_worker().user), assignment).status_code == 403
    assert contest(APIClient(), assignment).status_code == 403
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.AWAITING_VALIDATION


def test_worker_sees_contested_status_and_company_reason():
    assignment = contested_assignment()

    data = client_for(assignment.worker.user).get("/api/workers/me/jobs/").json()

    (item,) = data["groups"]["in_progress"]
    assert item["status_label"] == "Contestada"
    assert item["contest_reason"] == REASON


def test_admin_decides_for_worker_and_payment_is_settled_97_3():
    assignment = contested_assignment()
    client = admin_client()

    response = client.post(
        resolve_url(assignment), {"decision": "worker", "reason": "Horas conferidas"}
    )

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.PAID
    assert entries(assignment.vacancy.custody) == {
        "RETENCAO": 10000,
        "REPASSE_PRESTADOR": 9700,
        "TAXA_PLATAFORMA": 300,
    }
    assert Notification.objects.filter(
        user=assignment.worker.user, kind="CONTESTACAO_RESOLVIDA"
    ).exists()


def test_admin_decides_for_company_refunds_position_and_notifies_both():
    assignment = contested_assignment()
    client = admin_client()

    response = client.post(
        resolve_url(assignment), {"decision": "company", "reason": "Procede"}
    )

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.REFUNDED
    assert entries(assignment.vacancy.custody) == {
        "RETENCAO": 10000,
        "ESTORNO_CONTRATANTE": 10000,
    }
    company_user = assignment.vacancy.company.members.first().user
    assert Notification.objects.filter(
        user=assignment.worker.user, kind="CONTESTACAO_RESOLVIDA"
    ).exists()
    assert Notification.objects.filter(user=company_user, kind="CONTESTACAO_RESOLVIDA").exists()


def test_admin_decision_requires_reason():
    assignment = contested_assignment()

    response = admin_client().post(resolve_url(assignment), {"decision": "worker", "reason": " "})

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONTESTED


def test_only_admin_resolves():
    assignment = contested_assignment()
    anonymous = Client()
    company = Client()
    company.force_login(assignment.vacancy.company.members.first().user)

    for client in (anonymous, company):
        response = client.post(resolve_url(assignment), {"decision": "worker", "reason": "x"})
        assert response.status_code in (302, 403)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONTESTED


def test_admin_resolution_form_shows_company_reason():
    assignment = contested_assignment()
    response = admin_client().get(resolve_url(assignment))
    assert response.status_code == 200
    content = response.content.decode()
    assert REASON in content
    assert "Decidir a favor do prestador" in content
    assert "Decidir a favor da empresa" in content


def test_admin_highlights_contests_open_for_more_than_48_hours():
    old = contested_assignment()
    recent = contested_assignment()
    StateTransition.objects.filter(
        entity_type="Assignment", entity_id=old.pk, to_state="CONTESTADA"
    ).update(created_at=timezone.now() - timedelta(hours=49))
    client = admin_client()

    page = client.get("/admin/vacancies/assignment/").content.decode()
    assert "mais de 48 h" in page

    filtered = client.get("/admin/vacancies/assignment/?contestacao=atrasada").content.decode()
    assert f"/admin/vacancies/assignment/{old.pk}/resolver-contestacao/" in filtered
    assert f"/admin/vacancies/assignment/{recent.pk}/resolver-contestacao/" not in filtered
