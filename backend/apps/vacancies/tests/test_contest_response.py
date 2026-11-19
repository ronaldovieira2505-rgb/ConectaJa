"""US58: prestador responde à contestação de horas com a sua versão."""

import pytest

from apps.core.models import Notification, StateTransition
from apps.core.tests.factories import make_admin, make_company, make_worker
from apps.vacancies import assignment_services as assignments
from apps.vacancies import history
from apps.vacancies.models import Assignment
from apps.vacancies.tests.test_contest_api import (
    admin_client,
    contested_assignment,
    resolve_url,
)
from apps.vacancies.tests.test_validation_api import (
    awaiting_assignment,
    client_for,
    company_client,
)

pytestmark = pytest.mark.django_db

TEXT = "Cumpri o horário inteiro e o encarregado assinou a minha saída."
JOBS_URL = "/api/workers/me/jobs/"


def respond(client, assignment, text=TEXT):
    return client.post(
        f"/api/assignments/{assignment.pk}/contest-response/", {"text": text}, format="json"
    )


def worker_client(assignment):
    return client_for(assignment.worker.user)


def job(client, assignment):
    groups = client.get(JOBS_URL).json()["groups"]
    return next(
        i
        for g in groups.values()
        for i in g
        if i["id"] == assignment.pk and i["kind"] == "assignment"
    )


def test_worker_sees_company_reason_and_can_respond_in_my_jobs():
    assignment = contested_assignment()

    item = job(worker_client(assignment), assignment)

    assert item["status"] == "CONTESTADA"
    assert item["contest_reason"] == "O prestador saiu duas horas antes."
    assert item["can_respond_to_contest"] is True
    assert item["contest_response"] == ""
    assert item["contest_response_at"] is None


def test_response_is_saved_with_timestamp_and_visible_to_worker():
    assignment = contested_assignment()
    client = worker_client(assignment)

    response = respond(client, assignment)

    assert response.status_code == 200, response.content
    assignment.refresh_from_db()
    assert assignment.contest_response == TEXT
    assert assignment.contest_response_at is not None
    item = job(client, assignment)
    assert item["contest_response"] == TEXT
    assert item["contest_response_at"] is not None
    assert item["can_respond_to_contest"] is False


def test_response_notifies_admins_and_company():
    assignment = contested_assignment()
    admin = make_admin()

    respond(worker_client(assignment), assignment)

    assert Notification.objects.filter(user=admin, kind="CONTESTACAO_RESPOSTA").exists()
    member = assignment.vacancy.company.members.first().user
    assert Notification.objects.filter(user=member, kind="CONTESTACAO_RESPOSTA").exists()


@pytest.mark.parametrize("text", ["", "   ", "curto", "123456789", "x" * 1001, None, 123])
def test_invalid_text_is_rejected_and_nothing_is_saved(text):
    assignment = contested_assignment()
    admin = make_admin()

    response = respond(worker_client(assignment), assignment, text)

    assert response.status_code == 400
    assert response.json()["detail"] == "A sua versão deve ter de 10 a 1.000 caracteres."
    assignment.refresh_from_db()
    assert assignment.contest_response == ""
    assert assignment.contest_response_at is None
    assert not Notification.objects.filter(user=admin, kind="CONTESTACAO_RESPOSTA").exists()


@pytest.mark.parametrize("size", [10, 1000])
def test_limits_are_inclusive(size):
    assignment = contested_assignment()

    assert respond(worker_client(assignment), assignment, "a" * size).status_code == 200


def test_response_is_single_and_definitive():
    assignment = contested_assignment()
    client = worker_client(assignment)
    assert respond(client, assignment).status_code == 200

    again = respond(client, assignment, "Outra versão dos fatos, bem diferente.")

    assert again.status_code == 409
    assignment.refresh_from_db()
    assert assignment.contest_response == TEXT


def test_response_does_not_change_state_nor_create_transition():
    assignment = contested_assignment()
    before = StateTransition.objects.filter(
        entity_type="Assignment", entity_id=assignment.pk
    ).count()

    respond(worker_client(assignment), assignment)

    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONTESTED
    after = StateTransition.objects.filter(
        entity_type="Assignment", entity_id=assignment.pk
    ).count()
    assert after == before


@pytest.mark.parametrize("favor_worker", [True, False])
def test_cannot_respond_after_admin_decides_but_old_response_stays_visible(favor_worker):
    assignment = contested_assignment()
    client = worker_client(assignment)
    respond(client, assignment)
    assignments.resolve_contest(
        assignment, in_favor_of_worker=favor_worker, reason="Decisão.", actor=make_admin()
    )
    assignment.refresh_from_db()

    assert respond(client, assignment, "Tentando responder depois da decisão.").status_code == 409
    assignment.refresh_from_db()
    assert assignment.contest_response == TEXT
    assert job(client, assignment)["contest_response"] == TEXT


def test_cannot_respond_after_decision_without_previous_response():
    assignment = contested_assignment()
    assignments.resolve_contest(
        assignment, in_favor_of_worker=True, reason="Decisão.", actor=make_admin()
    )

    response = respond(worker_client(assignment), assignment)

    assert response.status_code == 409
    assignment.refresh_from_db()
    assert assignment.contest_response_at is None


def test_not_contested_assignment_does_not_accept_response():
    assignment = awaiting_assignment()

    assert respond(worker_client(assignment), assignment).status_code == 409


def test_only_the_assignment_worker_can_respond():
    assignment = contested_assignment()
    other = make_worker()

    assert respond(client_for(other.user), assignment).status_code == 404
    assert respond(company_client(assignment.vacancy.company), assignment).status_code == 403
    assignment.refresh_from_db()
    assert assignment.contest_response_at is None


def test_admin_sees_response_next_to_company_reason():
    assignment = contested_assignment()
    respond(worker_client(assignment), assignment)

    page = admin_client().get(resolve_url(assignment))

    html = page.content.decode()
    assert "O prestador saiu duas horas antes." in html
    assert TEXT in html
    assert "Enviada em" in html


def test_admin_page_says_when_worker_did_not_respond():
    assignment = contested_assignment()

    html = admin_client().get(resolve_url(assignment)).content.decode()

    assert "O prestador ainda não respondeu." in html


def test_admin_list_shows_response():
    assignment = contested_assignment()
    respond(worker_client(assignment), assignment)

    html = admin_client().get("/admin/vacancies/assignment/").content.decode()

    assert TEXT in html


def test_company_sees_response_in_contested_detail():
    assignment = contested_assignment()
    company = company_client(assignment.vacancy.company)

    before = company.get("/api/company/assignments/pending/").json()["contested"][0]
    assert before["contest_response"] == ""
    respond(worker_client(assignment), assignment)
    after = company.get("/api/company/assignments/pending/").json()["contested"][0]

    assert after["id"] == assignment.pk
    assert after["contest_reason"] == "O prestador saiu duas horas antes."
    assert after["contest_response"] == TEXT
    assert after["contest_response_at"] is not None


def test_other_company_does_not_see_contested_assignment():
    contested_assignment()
    other = make_company()

    body = company_client(other).get("/api/company/assignments/pending/").json()

    assert body["contested"] == []


def test_timeline_records_worker_response_with_date_and_time():
    assignment = contested_assignment()
    respond(worker_client(assignment), assignment)
    assignment.refresh_from_db()

    events = history.build_history(assignment.vacancy)

    found = [e for e in events if "Prestador respondeu à contestação" in e.description]
    assert len(found) == 1
    assert found[0].at == assignment.contest_response_at
    assert found[0].reason == TEXT
    assert found[0].actor.startswith("Prestador")
