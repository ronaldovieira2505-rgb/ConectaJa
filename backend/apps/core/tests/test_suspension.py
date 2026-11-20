"""US76: suspender e reativar contas manualmente."""

from datetime import timedelta

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.core.models import Notification, StateTransition
from apps.core.suspension import reactivate_account, suspend_account
from apps.core.tests.factories import (
    NOW,
    make_admin,
    make_assignment,
    make_company,
    make_published_vacancy,
    make_user,
    make_worker,
    vacancy_fields,
)
from apps.vacancies import application_services as applications
from apps.vacancies import services as vacancies
from apps.vacancies.models import Assignment

pytestmark = pytest.mark.django_db


def audit(entity_type, pk):
    return StateTransition.objects.filter(entity_type=entity_type, entity_id=pk).order_by("id")


# --- prestador ---------------------------------------------------------------------------


def test_admin_suspends_worker_for_days_with_audit_and_notification():
    admin, worker = make_admin(), make_worker()
    suspend_account(worker, actor=admin, reason="Conduta inadequada", days=10, now=NOW)
    worker.refresh_from_db()
    assert worker.suspended_until == NOW + timedelta(days=10)
    assert not worker.suspension_indefinite
    assert worker.is_suspended(NOW)
    log = audit("WorkerSuspension", worker.pk).get()
    assert (log.from_state, log.to_state, log.actor, log.reason) == (
        "ATIVO",
        "SUSPENSO",
        admin,
        "Conduta inadequada",
    )
    note = Notification.objects.get(user=worker.user)
    assert "Conduta inadequada" in note.message
    assert "11/11/2026" in note.message


def test_admin_suspends_worker_indefinitely():
    worker = make_worker()
    suspend_account(worker, actor=make_admin(), reason="Fraude", indefinite=True, now=NOW)
    worker.refresh_from_db()
    assert worker.suspended_until is None
    assert worker.is_suspended(NOW + timedelta(days=5000))
    assert "indeterminado" in Notification.objects.get(user=worker.user).message


@pytest.mark.parametrize("days", [0, 366, -1, None, True])
def test_invalid_days_change_nothing(days):
    worker = make_worker()
    with pytest.raises(DomainError):
        suspend_account(worker, actor=make_admin(), reason="x", days=days, now=NOW)
    worker.refresh_from_db()
    assert not worker.is_suspended(NOW)
    assert not StateTransition.objects.filter(entity_type="WorkerSuspension").exists()


@pytest.mark.parametrize("days", [1, 365])
def test_day_limits_are_accepted(days):
    worker = make_worker()
    suspend_account(worker, actor=make_admin(), reason="x", days=days, now=NOW)
    worker.refresh_from_db()
    assert worker.suspended_until == NOW + timedelta(days=days)


def test_days_and_indefinite_together_are_rejected():
    with pytest.raises(DomainError):
        suspend_account(
            make_worker(), actor=make_admin(), reason="x", days=3, indefinite=True, now=NOW
        )


@pytest.mark.parametrize("reason", ["", "   ", None])
def test_empty_reason_returns_error_and_changes_nothing(reason):
    worker, admin = make_worker(), make_admin()
    with pytest.raises(DomainError):
        suspend_account(worker, actor=admin, reason=reason, days=5, now=NOW)
    worker.refresh_from_db()
    assert not worker.is_suspended(NOW)
    assert not Notification.objects.filter(user=worker.user).exists()
    with pytest.raises(DomainError):
        reactivate_account(worker, actor=admin, reason=reason, now=NOW)


def test_cannot_suspend_twice():
    worker, admin = make_worker(), make_admin()
    suspend_account(worker, actor=admin, reason="x", days=5, now=NOW)
    with pytest.raises(DomainError):
        suspend_account(worker, actor=admin, reason="y", days=9, now=NOW)


@pytest.mark.parametrize("indefinite", [False, True])
def test_reactivate_ends_suspension_now_with_audit_and_notification(indefinite):
    worker, admin = make_worker(), make_admin()
    suspend_account(
        worker, actor=admin, reason="x", days=None if indefinite else 30, indefinite=indefinite,
        now=NOW,
    )
    reactivate_account(worker, actor=admin, reason="Recurso aceito", now=NOW)
    worker.refresh_from_db()
    assert not worker.is_suspended(NOW)
    assert worker.suspended_until is None and not worker.suspension_indefinite
    last = audit("WorkerSuspension", worker.pk).last()
    assert (last.from_state, last.to_state, last.actor, last.reason) == (
        "SUSPENSO",
        "ATIVO",
        admin,
        "Recurso aceito",
    )
    assert Notification.objects.filter(user=worker.user, title="Conta reativada").exists()


def test_reactivate_lifts_automatic_suspension_too():
    worker = make_worker(suspended_until=NOW + timedelta(days=15))
    reactivate_account(worker, actor=make_admin(), reason="Falta justificada", now=NOW)
    worker.refresh_from_db()
    assert worker.suspended_until is None


def test_reactivate_requires_suspended_account():
    with pytest.raises(DomainError):
        reactivate_account(make_worker(), actor=make_admin(), reason="x", now=NOW)


def test_suspended_worker_cannot_apply_or_be_approved_but_keeps_confirmed_assignment():
    assignment = make_assignment()
    worker = assignment.worker
    other = make_published_vacancy(starts_in_hours=100)
    pending = applications.apply_to_vacancy(other, worker, now=NOW)
    suspend_account(worker, actor=make_admin(), reason="x", indefinite=True, now=NOW)
    worker.refresh_from_db()
    with pytest.raises(DomainError):
        applications.apply_to_vacancy(make_published_vacancy(starts_in_hours=200), worker, now=NOW)
    with pytest.raises(DomainError):
        applications.approve_application(pending, actor=None, now=NOW)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED


# --- empresa -----------------------------------------------------------------------------


def test_admin_suspends_company_with_audit_and_notification():
    admin, company = make_admin(), make_company()
    suspend_account(company, actor=admin, reason="Denúncias", days=7, now=NOW)
    company.refresh_from_db()
    assert company.suspended_until == NOW + timedelta(days=7)
    log = audit("CompanySuspension", company.pk).get()
    assert (log.from_state, log.to_state, log.actor) == ("ATIVO", "SUSPENSO", admin)
    member = company.members.get().user
    assert "Denúncias" in Notification.objects.get(user=member).message


def test_suspended_company_cannot_create_or_pay_but_published_vacancies_stay():
    company = make_company()
    published = make_published_vacancy(company=company)
    unpaid = vacancies.create_vacancy(
        company=company, now=NOW, **vacancy_fields(NOW + timedelta(hours=60))
    )
    suspend_account(company, actor=make_admin(), reason="x", days=7, now=NOW)
    company.refresh_from_db()
    with pytest.raises(DomainError, match="Conta suspensa até"):
        vacancies.create_vacancy(
            company=company, now=NOW, **vacancy_fields(NOW + timedelta(hours=70))
        )
    unpaid.refresh_from_db()
    with pytest.raises(DomainError, match="Conta suspensa até"):
        vacancies.pay_vacancy(unpaid, now=NOW)
    published.refresh_from_db()
    assert published.status == "PUBLICADA"


def test_company_api_blocks_with_notice_and_me_shows_it(client):
    company = make_company()
    suspend_account(company, actor=make_admin(), reason="x", indefinite=True)
    client.force_login(company.members.get().user)
    body = {
        **vacancy_fields(NOW + timedelta(hours=60)),
        "starts_at": (NOW + timedelta(days=30)).isoformat(),
        "ends_at": (NOW + timedelta(days=30, hours=4)).isoformat(),
    }
    response = client.post("/api/vacancies/", body, content_type="application/json")
    assert response.status_code == 403
    assert "suspensa" in response.json()["detail"]
    me = client.get("/api/companies/me/").json()
    assert me["is_suspended"] is True
    assert me["suspension_message"].startswith("Conta suspensa")


def test_reactivated_company_publishes_again_and_is_notified():
    company, admin = make_company(), make_admin()
    suspend_account(company, actor=admin, reason="x", days=7, now=NOW)
    reactivate_account(company, actor=admin, reason="Regularizada", now=NOW)
    company.refresh_from_db()
    make_published_vacancy(company=company)
    member = company.members.get().user
    assert Notification.objects.filter(user=member, title="Conta reativada").exists()


# --- permissões e painel -----------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.WORKER, Role.COMPANY])
def test_only_admin_can_suspend_or_reactivate(role):
    worker = make_worker()
    with pytest.raises(DomainError):
        suspend_account(worker, actor=make_user(role), reason="x", days=3, now=NOW)
    with pytest.raises(DomainError):
        suspend_account(worker, actor=None, reason="x", days=3, now=NOW)
    suspend_account(worker, actor=make_admin(), reason="x", days=3, now=NOW)
    with pytest.raises(DomainError):
        reactivate_account(worker, actor=make_user(role), reason="x", now=NOW)


def test_panel_suspend_and_reactivate_worker(client):
    worker = make_worker()
    client.force_login(make_admin())
    url = reverse("admin:workers_worker_suspend", args=[worker.pk])
    assert client.get(url).status_code == 200
    # motivo vazio: erro e nada muda
    client.post(url, {"reason": " ", "days": 5})
    worker.refresh_from_db()
    assert worker.suspended_until is None
    assert client.post(url, {"reason": "Abuso", "days": 5}).status_code == 302
    worker.refresh_from_db()
    assert worker.suspended_until is not None
    url = reverse("admin:workers_worker_reactivate", args=[worker.pk])
    assert client.post(url, {"reason": "Ok"}).status_code == 302
    worker.refresh_from_db()
    assert worker.suspended_until is None


def test_panel_suspend_company_indefinitely(client):
    company = make_company()
    client.force_login(make_admin())
    url = reverse("admin:companies_company_suspend", args=[company.pk])
    assert client.post(url, {"reason": "Abuso", "indefinite": "on"}).status_code == 302
    company.refresh_from_db()
    assert company.suspension_indefinite


def test_panel_denies_non_admin(client):
    worker = make_worker()
    client.force_login(make_user(Role.COMPANY))
    url = reverse("admin:workers_worker_suspend", args=[worker.pk])
    assert client.post(url, {"reason": "x", "days": 3}).status_code in (302, 403)
    worker.refresh_from_db()
    assert worker.suspended_until is None
