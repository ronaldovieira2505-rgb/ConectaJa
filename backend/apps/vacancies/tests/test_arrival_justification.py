"""US51: justificar a chegada quando o check-in pelo celular não funciona."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.deadlines import process_deadlines
from apps.core.exceptions import DomainError
from apps.core.models import Notification, PlatformParameters, StateTransition
from apps.core.tests.factories import LAT, LNG, make_admin, make_assignment, make_company
from apps.vacancies import arrival
from apps.vacancies import assignment_services as assignments
from apps.vacancies.models import ArrivalJustification, Assignment

pytestmark = pytest.mark.django_db

J = ArrivalJustification.Status
PENDING_URL = "/api/company/assignments/pending/"


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def company_client(company):
    return client_for(company.members.first().user)


def assignment_starting_in(minutes, **kw):
    """Alocação CONFIRMADA cujo turno começa daqui a `minutes` (pode ser negativo)."""
    now = timezone.now()
    assignment = make_assignment(now=now, starts_in_hours=48, **kw)
    vacancy = assignment.vacancy
    vacancy.starts_at = now + timedelta(minutes=minutes)
    vacancy.ends_at = vacancy.starts_at + timedelta(hours=4)
    vacancy.save()
    return assignment


def justify(assignment, reason="GPS", text="O GPS não pega aqui dentro."):
    return client_for(assignment.worker.user).post(
        f"/api/assignments/{assignment.pk}/arrival-justification/",
        {"reason": reason, "text": text},
        format="json",
    )


def decide(assignment, company=None, **data):
    company = company or assignment.vacancy.company
    return company_client(company).post(
        f"/api/assignments/{assignment.pk}/arrival-justification/decide/", data, format="json"
    )


def job(assignment):
    client = client_for(assignment.worker.user)
    groups = client.get("/api/workers/me/jobs/").json()["groups"]
    items = [i for g in groups.values() for i in g if i["kind"] == "assignment"]
    return next(i for i in items if i["id"] == assignment.pk)


# Janela -------------------------------------------------------------------------------------


def test_button_only_inside_check_in_window():
    params = PlatformParameters.get()
    inside = assignment_starting_in(10)
    too_early = assignment_starting_in(params.checkin_open_minutes_before + 30)
    assert job(inside)["can_justify_arrival"] is True
    assert job(inside)["arrival_justification"] is None
    assert job(too_early)["can_justify_arrival"] is False


def test_submit_outside_window_is_refused():
    params = PlatformParameters.get()
    assignment = assignment_starting_in(params.checkin_open_minutes_before + 30)
    response = justify(assignment)
    assert response.status_code == 409
    assert "janela" in response.json()["detail"]
    assert not ArrivalJustification.objects.exists()


def test_submit_after_tolerance_is_refused():
    params = PlatformParameters.get()
    assignment = assignment_starting_in(-(params.no_show_tolerance_minutes + 5))
    assert justify(assignment).status_code == 409


# Envio pelo prestador ----------------------------------------------------------------------


def test_worker_sends_justification_and_company_is_notified():
    assignment = assignment_starting_in(5)
    response = justify(assignment, reason="BATERIA", text="")
    assert response.status_code == 200
    body = response.json()
    assert body["can_justify_arrival"] is False
    assert body["can_check_in"] is True  # ainda pode tentar o check-in normal
    assert body["arrival_justification"]["status"] == J.PENDING
    assert body["arrival_justification"]["reason_label"] == "Celular sem bateria"

    company_user = assignment.vacancy.company.members.first().user
    note = Notification.objects.get(user=company_user, kind="JUSTIFICATIVA_CHEGADA")
    assert note.link == "/empresa/confirmar-presenca"

    pending = company_client(assignment.vacancy.company).get(PENDING_URL).json()
    [item] = pending["arrival_justifications"]
    assert item["assignment_id"] == assignment.pk
    assert item["reason"] == "BATERIA"
    assert item["worker_first_name"] == "Prestador"


@pytest.mark.parametrize(
    ("reason", "text"),
    [("OUTRO", ""), ("OUTRO", "   "), ("INVALIDO", "x"), ("GPS", "x" * 301), ("GPS", 123)],
)
def test_invalid_justification_is_refused(reason, text):
    assignment = assignment_starting_in(5)
    assert justify(assignment, reason=reason, text=text).status_code == 409
    assert not ArrivalJustification.objects.exists()


def test_text_up_to_300_characters_is_accepted():
    assignment = assignment_starting_in(5)
    assert justify(assignment, reason="OUTRO", text="x" * 300).status_code == 200


def test_only_one_justification_per_assignment():
    assignment = assignment_starting_in(5)
    assert justify(assignment).status_code == 200
    response = justify(assignment)
    assert response.status_code == 409
    assert ArrivalJustification.objects.count() == 1


def test_only_confirmed_assignment_can_be_justified():
    assignment = assignment_starting_in(5)
    assignments.check_in(assignment, lat=LAT, lng=LNG)
    assert justify(assignment).status_code == 409


def test_other_worker_cannot_justify():
    assignment = assignment_starting_in(5)
    other = assignment_starting_in(5)
    response = client_for(other.worker.user).post(
        f"/api/assignments/{assignment.pk}/arrival-justification/",
        {"reason": "GPS"},
        format="json",
    )
    assert response.status_code == 404


# Decisão da empresa ------------------------------------------------------------------------


def test_company_confirms_arrival_with_request_time_as_check_in():
    assignment = assignment_starting_in(5)
    justify(assignment)
    justification = ArrivalJustification.objects.get()
    response = decide(assignment, confirm=True)
    assert response.status_code == 200
    assert response.json()["status"] == J.CONFIRMED
    assert response.json()["assignment_status"] == Assignment.Status.IN_PROGRESS

    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.IN_PROGRESS
    assert assignment.check_in_at == justification.created_at
    assert assignment.check_in_confirmed_by_company is True
    assert assignment.check_in_lat is None
    log = StateTransition.objects.get(
        entity_type="Assignment", to_state=Assignment.Status.IN_PROGRESS
    )
    assert log.reason == "Check-in confirmado pela empresa"
    assert Notification.objects.filter(
        user=assignment.worker.user, title="Chegada confirmada"
    ).exists()
    assert job(assignment)["check_in_confirmed_by_company"] is True
    assert decide(assignment, confirm=True).status_code == 409  # já decidida


def test_company_refuses_with_reason_and_worker_stays_confirmed():
    assignment = assignment_starting_in(5)
    justify(assignment)
    assert decide(assignment, confirm=False, reason="  ").status_code == 400
    assert decide(assignment, confirm="sim").status_code == 400

    response = decide(assignment, confirm=False, reason="Ninguém chegou ao portão.")
    assert response.status_code == 200
    assert response.json()["status"] == J.REFUSED
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED
    note = Notification.objects.get(user=assignment.worker.user, kind="JUSTIFICATIVA_CHEGADA")
    assert "Ninguém chegou ao portão." in note.message
    assert job(assignment)["arrival_justification"]["decision_reason"] == (
        "Ninguém chegou ao portão."
    )

    # Recusada: volta a valer a regra de falta.
    params = PlatformParameters.get()
    later = assignment.vacancy.starts_at + timedelta(minutes=params.no_show_tolerance_minutes + 1)
    process_deadlines(now=later)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.NO_SHOW


def test_other_company_cannot_decide():
    assignment = assignment_starting_in(5)
    justify(assignment)
    assert decide(assignment, company=make_company(), confirm=True).status_code == 404


def test_decision_without_justification_is_404():
    assignment = assignment_starting_in(5)
    assert decide(assignment, confirm=True).status_code == 404


def test_normal_check_in_after_request_leaves_nothing_to_decide():
    assignment = assignment_starting_in(5)
    justify(assignment)
    assignments.check_in(assignment, lat=LAT, lng=LNG)
    pending = company_client(assignment.vacancy.company).get(PENDING_URL).json()
    assert pending["arrival_justifications"] == []
    assert decide(assignment, confirm=True).status_code == 409
    assert arrival.escalate_overdue(now=assignment.vacancy.ends_at) == 0


# Falta suspensa e envio ao admin -----------------------------------------------------------


def test_pending_request_suspends_automatic_no_show():
    assignment = assignment_starting_in(5)
    justify(assignment)
    params = PlatformParameters.get()
    later = assignment.vacancy.starts_at + timedelta(minutes=params.no_show_tolerance_minutes + 1)
    process_deadlines(now=later)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED


def test_without_answer_until_shift_end_request_goes_to_admin():
    admin = make_admin()
    assignment = assignment_starting_in(5)
    justify(assignment)
    ends_at = assignment.vacancy.ends_at

    assert (
        process_deadlines(now=ends_at - timedelta(minutes=1)).get("justificativas_para_admin")
        is None
    )
    done = process_deadlines(now=ends_at)
    assert done["justificativas_para_admin"] == 1
    justification = ArrivalJustification.objects.get()
    assert justification.status == J.ADMIN
    assert Notification.objects.filter(user=admin, kind="JUSTIFICATIVA_CHEGADA").count() == 1

    # Idempotente e ainda sem falta automática; a empresa já não decide.
    later = ends_at + timedelta(hours=2)
    assert process_deadlines(now=later).get("justificativas_para_admin") is None
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED
    assert decide(assignment, confirm=True).status_code == 409
    pending = company_client(assignment.vacancy.company).get(PENDING_URL).json()
    assert pending["arrival_justifications"] == []


def _escalated(assignment):
    justify(assignment)
    arrival.escalate_overdue(now=assignment.vacancy.ends_at)
    return ArrivalJustification.objects.get(assignment=assignment)


def test_admin_confirms_presence():
    admin = make_admin()
    assignment = assignment_starting_in(5)
    justification = _escalated(assignment)
    arrival.decide_by_admin(justification, presence=True, actor=admin)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.IN_PROGRESS
    assert assignment.check_in_at == justification.created_at
    justification.refresh_from_db()
    assert justification.status == J.CONFIRMED
    assert justification.decided_by == admin
    # O turno já acabou: o check-out automático segue o fluxo normal.
    params = PlatformParameters.get()
    after = assignment.vacancy.ends_at + timedelta(
        minutes=params.auto_checkout_minutes_after_end + 1
    )
    process_deadlines(now=after)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.AWAITING_VALIDATION


def test_admin_confirms_no_show():
    admin = make_admin()
    assignment = assignment_starting_in(5)
    justification = _escalated(assignment)
    arrival.decide_by_admin(justification, presence=False, actor=admin)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.NO_SHOW
    log = StateTransition.objects.get(entity_type="Assignment", to_state=Assignment.Status.NO_SHOW)
    assert log.actor == admin
    assert log.reason == "Falta confirmada pelo admin"
    justification.refresh_from_db()
    assert justification.status == J.REFUSED


def test_admin_cannot_decide_request_still_with_company():
    assignment = assignment_starting_in(5)
    justify(assignment)
    justification = ArrivalJustification.objects.get()
    with pytest.raises(DomainError, match="não está com a equipe"):
        arrival.decide_by_admin(justification, presence=True, actor=make_admin())


def test_admin_action_in_django_admin():
    admin = make_admin()
    assignment = assignment_starting_in(5)
    justification = _escalated(assignment)
    response = client_for(admin).post(
        "/admin/vacancies/arrivaljustification/",
        {"action": "confirm_no_show", "_selected_action": [justification.pk]},
    )
    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.NO_SHOW
