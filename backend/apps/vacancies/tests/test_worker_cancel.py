"""US72: o prestador cancela a própria participação (com ou sem penalidade)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.exceptions import DomainError
from apps.core.models import Notification, PlatformParameters, StateTransition
from apps.core.tests.factories import make_assignment, make_published_vacancy, make_worker
from apps.vacancies import application_services as applications
from apps.vacancies.models import Application, Assignment
from apps.workers.services import apply_automatic_suspension

pytestmark = pytest.mark.django_db

S = Assignment.Status


def client_for(worker):
    client = APIClient()
    client.force_login(worker.user)
    return client


def assignment_starting_in(minutes, **kw):
    """Alocação CONFIRMADA cujo turno começa daqui a `minutes`."""
    now = timezone.now()
    assignment = make_assignment(now=now, starts_in_hours=48, **kw)
    vacancy = assignment.vacancy
    vacancy.starts_at = now + timedelta(minutes=minutes)
    vacancy.ends_at = vacancy.starts_at + timedelta(hours=4)
    vacancy.save()
    return assignment


def cancel(client, assignment):
    return client.post(f"/api/assignments/{assignment.pk}/cancel-by-worker/")


def job(client, assignment):
    groups = client.get("/api/workers/me/jobs/").json()["groups"]
    items = [i for g in groups.values() for i in g if i["kind"] == "assignment"]
    return next(i for i in items if i["id"] == assignment.pk)


def company_users(vacancy):
    return [member.user for member in vacancy.company.members.select_related("user")]


def test_early_cancel_has_no_penalty_and_releases_the_position():
    assignment = assignment_starting_in(48 * 60)
    worker, vacancy = assignment.worker, assignment.vacancy
    response = cancel(client_for(worker), assignment)
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "CANCELADA_PRESTADOR"
    assignment.refresh_from_db()
    worker.refresh_from_db()
    vacancy.refresh_from_db()
    assert assignment.status == S.CANCELLED_BY_WORKER
    assert worker.suspended_until is None
    assert vacancy.reopened is False
    assert vacancy.unavailable_positions == 0
    assert vacancy.accepts_applications(timezone.now())
    assert not StateTransition.objects.filter(entity_type="WorkerSuspension").exists()
    assert Notification.objects.filter(
        user__in=company_users(vacancy), kind="CANCELAMENTO_PRESTADOR"
    ).exists()
    # a empresa pode aprovar outro candidato
    other = make_worker()
    application = applications.apply_to_vacancy(vacancy, other)
    new_assignment = applications.approve_application(application)
    assert new_assignment.status == S.CONFIRMED


def test_early_cancel_leaves_a_state_transition():
    assignment = assignment_starting_in(48 * 60)
    cancel(client_for(assignment.worker), assignment)
    transition = StateTransition.objects.get(
        entity_type="Assignment", entity_id=assignment.pk, to_state="CANCELADA_PRESTADOR"
    )
    assert transition.from_state == "CONFIRMADA"
    assert transition.actor == assignment.worker.user


def test_late_cancel_blocks_the_worker_and_notifies():
    assignment = assignment_starting_in(10 * 60)
    worker = assignment.worker
    before = timezone.now()
    response = cancel(client_for(worker), assignment)
    assert response.status_code == 200, response.content
    assignment.refresh_from_db()
    worker.refresh_from_db()
    assert assignment.status == S.CANCELLED_BY_WORKER
    assert worker.suspended_until is not None
    assert (
        before + timedelta(days=7) - timedelta(minutes=1)
        <= worker.suspended_until
        <= timezone.now() + timedelta(days=7)
    )
    assert StateTransition.objects.filter(
        entity_type="WorkerSuspension", entity_id=worker.pk, reason="Cancelamento tardio"
    ).exists()
    assert Notification.objects.filter(user=worker.user, kind="CANCELAMENTO_TARDIO").exists()
    # bloqueado: não consegue se candidatar a outra vaga
    with pytest.raises(DomainError):
        applications.apply_to_vacancy(make_published_vacancy(now=timezone.now()), worker)


def test_late_cancel_block_days_comes_from_platform_parameters():
    PlatformParameters.objects.update(late_cancel_block_days=3, free_cancel_minutes_before=600)
    assignment = assignment_starting_in(5 * 60)
    client = client_for(assignment.worker)
    item = job(client, assignment)
    assert item["cancel_warning"] == "Cancelando agora você fica 3 dias sem poder se candidatar."
    cancel(client, assignment)
    assignment.worker.refresh_from_db()
    assert assignment.worker.suspended_until <= timezone.now() + timedelta(days=3)
    assert assignment.worker.suspended_until > timezone.now() + timedelta(days=2)


def test_jobs_list_warns_only_when_cancel_is_late():
    early = assignment_starting_in(48 * 60)
    item = job(client_for(early.worker), early)
    assert item["can_cancel"] is True and item["cancel_is_late"] is False
    assert item["cancel_warning"] == ""
    late = assignment_starting_in(10 * 60)
    item = job(client_for(late.worker), late)
    assert item["can_cancel"] is True and item["cancel_is_late"] is True
    assert item["cancel_warning"] == "Cancelando agora você fica 7 dias sem poder se candidatar."


def test_cancel_after_applications_closed_reopens_the_vacancy_as_urgent():
    assignment = assignment_starting_in(60)  # encerramento padrão: 120 min antes
    vacancy = assignment.vacancy
    assert cancel(client_for(assignment.worker), assignment).status_code == 200
    vacancy.refresh_from_db()
    assert vacancy.reopened is True
    assert vacancy.accepts_applications(timezone.now())
    other = make_worker()
    application = applications.apply_to_vacancy(vacancy, other)
    assert applications.approve_application(application).status == S.CONFIRMED


def test_cancel_before_applications_close_does_not_reopen():
    assignment = assignment_starting_in(10 * 60)
    cancel(client_for(assignment.worker), assignment)
    assignment.vacancy.refresh_from_db()
    assert assignment.vacancy.reopened is False


@pytest.mark.parametrize(
    "status",
    [
        S.IN_PROGRESS,
        S.AWAITING_VALIDATION,
        S.CONTESTED,
        S.APPROVED,
        S.PAID,
        S.NO_SHOW,
        S.REFUNDED,
        S.CANCELLED_BY_WORKER,
        S.CANCELLED_BY_COMPANY,
    ],
)
def test_cannot_cancel_outside_confirmed(status):
    assignment = assignment_starting_in(48 * 60)
    Assignment.objects.filter(pk=assignment.pk).update(status=status)
    client = client_for(assignment.worker)
    assert job(client, assignment)["can_cancel"] is False
    response = cancel(client, assignment)
    assert response.status_code == 409
    assignment.refresh_from_db()
    assert assignment.status == status
    assert assignment.worker.suspended_until is None


def test_pending_application_can_still_be_withdrawn_without_penalty():
    now = timezone.now()
    assignment = make_assignment(now=now)
    vacancy = assignment.vacancy
    vacancy.positions = 2
    vacancy.save()
    worker = make_worker()
    application = applications.apply_to_vacancy(vacancy, worker, now=now)
    response = client_for(worker).post(f"/api/applications/{application.pk}/withdraw/")
    assert response.status_code == 200
    application.refresh_from_db()
    worker.refresh_from_db()
    assert application.status == Application.Status.WITHDRAWN
    assert worker.suspended_until is None


def test_late_cancel_does_not_count_as_no_show():
    PlatformParameters.objects.update(no_show_limit=1)
    assignment = assignment_starting_in(10 * 60)
    worker = assignment.worker
    cancel(client_for(worker), assignment)
    worker.refresh_from_db()
    block = worker.suspended_until
    assert not StateTransition.objects.filter(entity_type="Assignment", to_state="FALTA").exists()
    worker.suspended_until = None
    worker.save()
    assert apply_automatic_suspension(worker) is False
    assert block is not None


def test_only_the_owner_can_cancel():
    assignment = assignment_starting_in(48 * 60)
    assert cancel(client_for(make_worker()), assignment).status_code == 404
    assert cancel(APIClient(), assignment).status_code == 403
    assignment.refresh_from_db()
    assert assignment.status == S.CONFIRMED
