"""US43: lista de espera com chamada automática."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.deadlines import process_deadlines
from apps.core.models import Notification, PlatformParameters, StateTransition
from apps.core.tests.factories import make_assignment, make_published_vacancy, make_worker
from apps.vacancies import application_services as applications
from apps.vacancies import assignment_services as assignments
from apps.vacancies import waitlist_services as waitlist
from apps.vacancies.models import Application, Assignment, Vacancy

pytestmark = pytest.mark.django_db

S = Assignment.Status
AP = Application.Status
KIND = "CHAMADO_LISTA_DE_ESPERA"


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def full_team(waiting=0, starts_in_minutes=48 * 60):
    """Vaga de 1 posição preenchida e `waiting` candidatos pendentes (lista de espera).

    Os candidatos se inscrevem antes de a vaga lotar; depois o início da vaga é movido para
    daqui a `starts_in_minutes` (pode ser negativo: turno em andamento).
    """
    now = timezone.now()
    vacancy = make_published_vacancy(now=now, starts_in_hours=48, positions=waiting + 1)
    assignment = make_assignment(vacancy=vacancy, now=now)
    workers = [make_worker() for _ in range(waiting)]
    for worker in workers:
        applications.apply_to_vacancy(vacancy, worker, now=now)
    Vacancy.objects.filter(pk=vacancy.pk).update(
        positions=1,
        starts_at=now + timedelta(minutes=starts_in_minutes),
        ends_at=now + timedelta(minutes=starts_in_minutes, hours=4),
    )
    vacancy.refresh_from_db()
    assignment.refresh_from_db()
    return assignment, vacancy, workers


def application_of(vacancy, worker):
    return Application.objects.get(vacancy=vacancy, worker=worker)


def company_users(vacancy):
    return [m.user for m in vacancy.company.members.select_related("user")]


def test_pending_applications_stay_valid_as_ordered_waitlist():
    _, vacancy, (first, second) = full_team(waiting=2)
    data = client_for(company_users(vacancy)[0]).get(
        f"/api/vacancies/{vacancy.pk}/candidates/"
    ).json()
    assert data["team_complete"] is True
    assert data["auto_call_waitlist"] is True
    assert [c["waitlist_position"] for c in data["candidates"]] == [1, 2]
    assert [c["id"] for c in data["candidates"]] == [
        application_of(vacancy, first).pk,
        application_of(vacancy, second).pk,
    ]
    assert application_of(vacancy, first).status == AP.PENDING


def test_no_waitlist_numbers_while_the_team_is_not_complete():
    vacancy = make_published_vacancy(now=timezone.now(), starts_in_hours=48, positions=2)
    applications.apply_to_vacancy(vacancy, make_worker())
    data = client_for(company_users(vacancy)[0]).get(
        f"/api/vacancies/{vacancy.pk}/candidates/"
    ).json()
    assert data["team_complete"] is False
    assert data["candidates"][0]["waitlist_position"] is None


def test_worker_sees_waitlist_position_in_my_jobs():
    _, _, (first, second) = full_team(waiting=2)
    waiting = client_for(second.user).get("/api/workers/me/jobs/").json()["groups"]["waiting"]
    assert waiting[0]["status_label"] == "Na lista de espera (posição 2)"
    assert waiting[0]["waitlist_position"] == 2
    waiting = client_for(first.user).get("/api/workers/me/jobs/").json()["groups"]["waiting"]
    assert waiting[0]["status_label"] == "Na lista de espera (posição 1)"


def test_cancel_by_worker_calls_first_in_line_automatically():
    assignment, vacancy, (first, second) = full_team(waiting=2)
    response = client_for(assignment.worker.user).post(
        f"/api/assignments/{assignment.pk}/cancel-by-worker/"
    )
    assert response.status_code == 200, response.content
    assert application_of(vacancy, first).status == AP.APPROVED
    assert application_of(vacancy, second).status == AP.PENDING
    assert Assignment.objects.get(application__worker=first).status == S.CONFIRMED
    note = Notification.objects.get(user=first.user, kind=KIND)
    assert note.title == "Você foi chamado da lista de espera"
    assert Notification.objects.filter(user__in=company_users(vacancy), kind=KIND).exists()
    transition = StateTransition.objects.get(
        entity_type="Application", entity_id=application_of(vacancy, first).pk, to_state="APROVADA"
    )
    assert transition.actor is None  # SISTEMA


def test_no_show_calls_first_in_line_automatically():
    assignment, vacancy, (first, second) = full_team(waiting=2, starts_in_minutes=-60)
    assignments.mark_no_show(assignment)
    assert application_of(vacancy, first).status == AP.APPROVED
    assert application_of(vacancy, second).status == AP.PENDING
    assert Notification.objects.filter(user=first.user, kind=KIND).exists()


def test_deadline_processing_calls_waitlist_after_a_no_show():
    _, vacancy, (first, second) = full_team(waiting=2, starts_in_minutes=-60)
    Vacancy.objects.filter(pk=vacancy.pk).update(status=Vacancy.Status.IN_PROGRESS)
    process_deadlines()
    assert application_of(vacancy, first).status == AP.APPROVED
    assert application_of(vacancy, second).status == AP.PENDING


def test_ineligible_first_is_skipped_and_stays_pending():
    assignment, vacancy, (first, second) = full_team(waiting=2)
    first.suspended_until = timezone.now() + timedelta(days=3)
    first.save()
    assignments.cancel_by_worker(assignment)
    assert application_of(vacancy, first).status == AP.PENDING
    assert application_of(vacancy, second).status == AP.APPROVED


@pytest.mark.parametrize("rule", ["pix", "unverified", "overlap"])
def test_each_eligibility_rule_skips_the_candidate(rule):
    assignment, vacancy, (first, second) = full_team(waiting=2)
    if rule == "pix":
        first.pix_key = ""
        first.save()
    elif rule == "unverified":
        first.verification_status = "REJEITADO"
        first.save()
    else:
        busy = make_published_vacancy(now=timezone.now(), starts_in_hours=48)
        Vacancy.objects.filter(pk=busy.pk).update(
            starts_at=vacancy.starts_at, ends_at=vacancy.ends_at
        )
        make_assignment(vacancy=Vacancy.objects.get(pk=busy.pk), worker=first)
    assignments.cancel_by_worker(assignment)
    assert application_of(vacancy, first).status == AP.PENDING
    assert application_of(vacancy, second).status == AP.APPROVED


def test_nobody_is_called_when_no_one_is_eligible():
    assignment, vacancy, (first,) = full_team(waiting=1)
    first.suspended_until = timezone.now() + timedelta(days=3)
    first.save()
    assignments.cancel_by_worker(assignment)
    assert application_of(vacancy, first).status == AP.PENDING
    assert vacancy.unavailable_positions == 0


def test_nobody_is_called_with_less_than_tolerance_to_the_end():
    PlatformParameters.objects.update(no_show_tolerance_minutes=30)
    assignment, vacancy, (first,) = full_team(waiting=1, starts_in_minutes=-60)
    now = timezone.now()
    Vacancy.objects.filter(pk=vacancy.pk).update(
        starts_at=now - timedelta(hours=3, minutes=45), ends_at=now + timedelta(minutes=15)
    )
    assignments.mark_no_show(Assignment.objects.get(pk=assignment.pk), now=now)
    assert application_of(vacancy, first).status == AP.PENDING


def test_nobody_is_called_when_vacancy_is_finished():
    _, vacancy, (first,) = full_team(waiting=1)
    Vacancy.objects.filter(pk=vacancy.pk).update(status=Vacancy.Status.FINISHED)
    vacancy.refresh_from_db()
    assert waitlist.call_from_waitlist(vacancy, was_full=True) == []
    assert application_of(vacancy, first).status == AP.PENDING


def test_company_cancelling_a_position_does_not_call_anyone():
    assignment, vacancy, (first,) = full_team(waiting=1)
    response = client_for(company_users(vacancy)[0]).post(
        f"/api/assignments/{assignment.pk}/cancel-by-company/",
        {"reason": "Mudança de planos"},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert application_of(vacancy, first).status == AP.PENDING
    assert not Notification.objects.filter(kind=KIND).exists()


def test_calling_twice_never_approves_two_for_the_same_position():
    assignment, vacancy, (first, second) = full_team(waiting=2)
    assignments.cancel_by_worker(assignment)
    again = waitlist.call_from_waitlist(Vacancy.objects.get(pk=vacancy.pk), was_full=True)
    assert again == []
    assert Assignment.objects.filter(vacancy=vacancy, status=S.CONFIRMED).count() == 1
    assert application_of(vacancy, second).status == AP.PENDING
    assert Notification.objects.filter(kind=KIND, user=first.user).count() == 1


def test_company_can_turn_off_automatic_call():
    assignment, vacancy, (first, _) = full_team(waiting=2)
    response = client_for(company_users(vacancy)[0]).post(
        f"/api/vacancies/{vacancy.pk}/waitlist-auto-call/", {"enabled": False}, format="json"
    )
    assert response.status_code == 200
    assert response.json() == {"auto_call_waitlist": False}
    assignments.cancel_by_worker(assignment)
    assert application_of(vacancy, first).status == AP.PENDING
    # a empresa ainda aprova manualmente
    assert applications.approve_application(application_of(vacancy, first)).status == S.CONFIRMED


def test_auto_call_is_on_by_default_and_toggle_is_protected():
    _, vacancy, _ = full_team()
    assert vacancy.auto_call_waitlist is True
    url = f"/api/vacancies/{vacancy.pk}/waitlist-auto-call/"
    worker_client = client_for(make_worker().user)
    assert worker_client.post(url, {"enabled": False}, format="json").status_code == 403
    outsider = client_for(company_users(make_published_vacancy(now=timezone.now()))[0])
    assert outsider.post(url, {"enabled": False}, format="json").status_code == 404
    mine = client_for(company_users(vacancy)[0])
    assert mine.post(url, {"enabled": "no"}, format="json").status_code == 400
    vacancy.refresh_from_db()
    assert vacancy.auto_call_waitlist is True


def test_pending_are_not_called_when_the_team_was_not_full():
    now = timezone.now()
    vacancy = make_published_vacancy(now=now, starts_in_hours=48, positions=2)
    first_assignment = make_assignment(vacancy=vacancy, now=now)
    waiting = make_worker()
    applications.apply_to_vacancy(vacancy, waiting, now=now)
    assignments.cancel_by_worker(first_assignment)
    assert application_of(vacancy, waiting).status == AP.PENDING
