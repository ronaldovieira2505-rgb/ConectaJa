"""US52: a empresa pede que o prestador fique mais tempo quando o serviço atrasar."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.deadlines import process_deadlines
from apps.core.models import Notification, PlatformParameters, StateTransition
from apps.core.tests.factories import LAT, LNG, make_assignment, make_company
from apps.payments.models import LedgerEntry
from apps.vacancies import assignment_services as assignments
from apps.vacancies import overtime
from apps.vacancies.models import OvertimeRequest

pytestmark = pytest.mark.django_db

OT = OvertimeRequest.Status


def company_client(company):
    client = APIClient()
    client.force_login(company.members.first().user)
    return client


def running_assignment(started_minutes_ago=60, hours=4):
    """Alocação EM_EXECUCAO: turno de `hours` h (R$ 100,00) que começou há pouco."""
    now = timezone.now()
    assignment = make_assignment(now=now, starts_in_hours=48)
    vacancy = assignment.vacancy
    vacancy.starts_at = now - timedelta(minutes=started_minutes_ago)
    vacancy.ends_at = vacancy.starts_at + timedelta(hours=hours)
    vacancy.save()
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=vacancy.starts_at)
    assignment.refresh_from_db()
    return assignment


def ask(assignment, company=None, **data):
    company = company or assignment.vacancy.company
    return company_client(company).post(
        f"/api/assignments/{assignment.pk}/overtime/", data, format="json"
    )


def team_member(assignment):
    client = company_client(assignment.vacancy.company)
    team = client.get(f"/api/vacancies/{assignment.vacancy_id}/candidates/").json()["team"]
    return next(m for m in team if m["id"] == assignment.pk)


def test_minimum_is_proportional_to_the_shift_hourly_rate():
    assignment = running_assignment(hours=4)  # R$ 100,00 por 4 h = R$ 25,00/h
    vacancy = assignment.vacancy
    assert overtime.min_amount_cents(vacancy, 30) == 1250
    assert overtime.min_amount_cents(vacancy, 60) == 2500
    assert overtime.min_amount_cents(vacancy, 240) == 10000
    vacancy.ends_at = vacancy.starts_at + timedelta(hours=3)  # 10000/180 por min: arredonda p/ cima
    assert overtime.min_amount_cents(vacancy, 30) == 1667


def test_company_asks_for_overtime_and_worker_is_notified():
    assignment = running_assignment()
    before = timezone.now()
    response = ask(assignment, minutes=90, amount_cents=4000)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == OT.AWAITING
    assert body["status_label"] == "Aguardando prestador"
    assert body["minutes_label"] == "1 h 30 min"
    assert body["net_cents"] == 3880

    request = OvertimeRequest.objects.get()
    params = PlatformParameters.get()
    window = timedelta(minutes=params.overtime_response_minutes)
    assert before + window <= request.expires_at <= timezone.now() + window
    note = Notification.objects.get(user=assignment.worker.user, kind="HORA_EXTRA")
    assert "1 h 30 min a mais" in note.message
    assert "R$ 40,00" in note.message
    assert note.link == "/meus-trabalhos"
    assert StateTransition.objects.filter(
        entity_type="OvertimeRequest", entity_id=request.pk, from_state="", to_state=OT.AWAITING
    ).exists()
    # Neste passo nada é cobrado.
    assert not LedgerEntry.objects.filter(kind="RETENCAO", amount_cents=4000).exists()


def test_amount_below_the_minimum_is_refused():
    assignment = running_assignment()
    response = ask(assignment, minutes=60, amount_cents=2499)
    assert response.status_code == 400
    assert "R$ 25,00" in response.json()["detail"]
    assert ask(assignment, minutes=60, amount_cents=2500).status_code == 201


@pytest.mark.parametrize("minutes", [0, 15, 45, 270, True, "60", None])
def test_duration_must_be_30_min_to_4_h_in_30_min_steps(minutes):
    assignment = running_assignment()
    assert ask(assignment, minutes=minutes, amount_cents=99999).status_code == 400
    assert not OvertimeRequest.objects.exists()


@pytest.mark.parametrize("amount", [0, -100, "5000", None, 12.5])
def test_amount_must_be_a_positive_integer(amount):
    assignment = running_assignment()
    assert ask(assignment, minutes=30, amount_cents=amount).status_code == 400


def test_only_in_progress_assignments_before_shift_end():
    now = timezone.now()
    confirmed = make_assignment(now=now, starts_in_hours=48)
    assert ask(confirmed, minutes=30, amount_cents=5000).status_code == 409

    finished = running_assignment(started_minutes_ago=300, hours=4)  # acabou há 1 h
    response = ask(finished, minutes=30, amount_cents=5000)
    assert response.status_code == 409
    assert "terminou" in response.json()["detail"]


def test_no_second_request_while_one_is_pending():
    assignment = running_assignment()
    assert ask(assignment, minutes=30, amount_cents=5000).status_code == 201
    response = ask(assignment, minutes=60, amount_cents=5000)
    assert response.status_code == 409
    assert "aguardando o prestador" in response.json()["detail"]
    assert OvertimeRequest.objects.count() == 1


def test_only_one_accepted_extension_per_assignment():
    assignment = running_assignment()
    OvertimeRequest.objects.create(
        assignment=assignment,
        minutes=30,
        amount_cents=5000,
        status=OT.ACCEPTED,
        expires_at=timezone.now(),
    )
    assert ask(assignment, minutes=30, amount_cents=5000).status_code == 409


def test_other_company_gets_404():
    assignment = running_assignment()
    assert ask(assignment, company=make_company(), minutes=30, amount_cents=5000).status_code == 404


def test_request_expires_after_response_window_and_nothing_is_charged():
    assignment = running_assignment()
    ask(assignment, minutes=30, amount_cents=5000)
    request = OvertimeRequest.objects.get()

    assert (
        process_deadlines(now=request.expires_at - timedelta(seconds=1)).get(
            "horas_extras_expiradas"
        )
        is None
    )
    done = process_deadlines(now=request.expires_at)
    assert done["horas_extras_expiradas"] == 1
    request.refresh_from_db()
    assert request.status == OT.EXPIRED
    company_user = assignment.vacancy.company.members.first().user
    note = Notification.objects.get(user=company_user, kind="HORA_EXTRA")
    assert "Nada foi cobrado" in note.message
    assert StateTransition.objects.filter(
        entity_type="OvertimeRequest", entity_id=request.pk, to_state=OT.EXPIRED, actor=None
    ).exists()
    # Idempotente.
    assert process_deadlines(now=request.expires_at).get("horas_extras_expiradas") is None
    # Expirado: a empresa pode pedir de novo.
    assert ask(assignment, minutes=30, amount_cents=5000).status_code == 201


def test_request_expires_at_shift_end_when_it_comes_first():
    assignment = running_assignment(started_minutes_ago=235, hours=4)  # faltam 5 min
    ask(assignment, minutes=30, amount_cents=5000)
    request = OvertimeRequest.objects.get()
    assert request.expires_at == assignment.vacancy.ends_at


def test_response_window_is_a_platform_parameter():
    params = PlatformParameters.get()
    params.overtime_response_minutes = 5
    params.save()
    assignment = running_assignment()
    before = timezone.now()
    ask(assignment, minutes=30, amount_cents=5000)
    request = OvertimeRequest.objects.get()
    assert request.expires_at <= timezone.now() + timedelta(minutes=5)
    assert request.expires_at >= before + timedelta(minutes=5)


def test_team_shows_the_button_options_and_the_pending_request():
    assignment = running_assignment()
    member = team_member(assignment)
    assert member["can_request_overtime"] is True
    assert member["overtime"] is None
    assert [o["minutes"] for o in member["overtime_options"]] == [
        30,
        60,
        90,
        120,
        150,
        180,
        210,
        240,
    ]
    assert member["overtime_options"][0] == {
        "minutes": 30,
        "label": "30 min",
        "min_amount_cents": 1250,
    }

    ask(assignment, minutes=60, amount_cents=3000)
    member = team_member(assignment)
    assert member["can_request_overtime"] is False
    assert member["overtime_options"] == []
    assert member["overtime"]["status"] == OT.AWAITING
    assert member["overtime"]["amount_cents"] == 3000


def test_confirmed_member_has_no_overtime_button():
    now = timezone.now()
    assignment = make_assignment(now=now, starts_in_hours=48)
    member = team_member(assignment)
    assert member["can_request_overtime"] is False
    assert member["overtime"] is None


def test_admin_edits_the_response_window_and_rejects_zero(client):
    from django.urls import reverse

    from apps.core.tests.factories import make_admin
    from apps.core.tests.test_shift_reminder import admin_payload

    client.force_login(make_admin())
    url = reverse("admin:core_platformparameters_change", args=[1])
    assert client.post(url, admin_payload(overtime_response_minutes=0)).status_code == 200
    assert PlatformParameters.get().overtime_response_minutes == 15
    assert client.post(url, admin_payload(overtime_response_minutes=10)).status_code == 302
    assert PlatformParameters.get().overtime_response_minutes == 10
