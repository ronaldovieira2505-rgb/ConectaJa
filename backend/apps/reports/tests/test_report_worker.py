"""US70: a empresa denuncia um comportamento inadequado do prestador."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.companies.models import CompanyMember
from apps.core.models import Notification, StateTransition
from apps.core.tests.factories import (
    LAT,
    LNG,
    make_admin,
    make_assignment,
    make_company,
    make_published_vacancy,
    make_user,
    make_worker,
)
from apps.payments.models import LedgerEntry
from apps.reports.models import Report
from apps.vacancies import application_services as applications
from apps.vacancies import assignment_services as assignments
from apps.vacancies.models import Assignment

pytestmark = pytest.mark.django_db

URL = "/api/reports/"
DESCRIPTION = "Foi grosseiro com a equipe e saiu antes da hora."


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def company_user(company):
    return company.members.first().user


def report(user, assignment_id, **data):
    payload = {
        "target_type": "PRESTADOR",
        "target_id": assignment_id,
        "reason": "COMPORTAMENTO",
        "description": DESCRIPTION,
        **data,
    }
    return client_for(user).post(URL, payload, format="json")


def an_assignment():
    return make_assignment(now=timezone.now(), starts_in_hours=48)


def test_company_reports_a_worker_linked_to_the_assignment():
    admin = make_admin()
    assignment = an_assignment()
    company = assignment.vacancy.company
    response = report(company_user(company), assignment.pk, reason="ASSEDIO")
    assert response.status_code == 201
    assert response.json()["detail"] == "Denúncia enviada. A equipe vai analisar."

    saved = Report.objects.get()
    assert saved.target_type == "PRESTADOR"
    assert saved.assignment == assignment
    assert saved.worker == assignment.worker
    assert saved.reporter == company_user(company)
    assert saved.reporter_company == company
    assert saved.company is None
    assert saved.get_reason_display() == "Assédio"
    note = Notification.objects.get(user=admin, kind="DENUNCIA")
    assert "Assédio" in note.message
    assert StateTransition.objects.filter(
        entity_type="Report", entity_id=saved.pk, to_state="ABERTA"
    ).exists()


def test_worker_is_not_notified():
    assignment = an_assignment()
    report(company_user(assignment.vacancy.company), assignment.pk)
    assert not Notification.objects.filter(user=assignment.worker.user, kind="DENUNCIA").exists()


@pytest.mark.parametrize(
    "status",
    [
        Assignment.Status.IN_PROGRESS,
        Assignment.Status.NO_SHOW,
        Assignment.Status.PAID,
        Assignment.Status.CANCELLED_BY_WORKER,
    ],
)
def test_any_status_after_confirmation_counts(status):
    assignment = an_assignment()
    Assignment.objects.filter(pk=assignment.pk).update(status=status)
    assert report(company_user(assignment.vacancy.company), assignment.pk).status_code == 201


def test_worker_who_never_worked_for_the_company_cannot_be_reported():
    assignment = an_assignment()  # alocação numa vaga de outra empresa
    other_company = make_company()
    assert report(company_user(other_company), assignment.pk).status_code == 404

    # Só candidato não basta: sem alocação, não há o que denunciar.
    vacancy = make_published_vacancy(company=other_company, now=timezone.now())
    applications.apply_to_vacancy(vacancy, make_worker(), now=timezone.now())
    assert report(company_user(other_company), 999999).status_code == 404
    assert not Report.objects.exists()


def test_one_open_report_per_company_and_assignment():
    assignment = an_assignment()
    company = assignment.vacancy.company
    assert report(company_user(company), assignment.pk).status_code == 201
    response = report(company_user(company), assignment.pk, reason="DANO_FURTO")
    assert response.status_code == 409

    # Outro membro da mesma empresa também não abre outra.
    colleague = make_user(Role.COMPANY)
    CompanyMember.objects.create(user=colleague, company=company)
    assert report(colleague, assignment.pk).status_code == 409

    Report.objects.update(status="PROCEDENTE")
    assert report(company_user(company), assignment.pk).status_code == 201


def test_another_assignment_of_the_same_worker_is_a_different_target():
    first = an_assignment()
    company = first.vacancy.company
    vacancy = make_published_vacancy(company=company, now=timezone.now(), starts_in_hours=96)
    second = make_assignment(vacancy=vacancy, worker=first.worker, now=timezone.now())
    assert report(company_user(company), first.pk).status_code == 201
    assert report(company_user(company), second.pk).status_code == 201


@pytest.mark.parametrize("reason", ["VAGA_FALSA", "PAGAMENTO_POR_FORA", "", None])
def test_reason_must_be_one_of_the_worker_reasons(reason):
    assignment = an_assignment()
    response = report(company_user(assignment.vacancy.company), assignment.pk, reason=reason)
    assert response.status_code == 400


@pytest.mark.parametrize("description", ["curto", "x" * 1001])
def test_description_from_10_to_1000_characters(description):
    assignment = an_assignment()
    company = assignment.vacancy.company
    response = report(company_user(company), assignment.pk, description=description)
    assert response.status_code == 400


def test_only_companies_report_workers():
    assignment = an_assignment()
    assert report(make_worker().user, assignment.pk).status_code == 403
    assert report(make_admin(), assignment.pk).status_code == 403
    anonymous = APIClient().post(
        URL,
        {
            "target_type": "PRESTADOR",
            "target_id": assignment.pk,
            "reason": "COMPORTAMENTO",
            "description": DESCRIPTION,
        },
        format="json",
    )
    assert anonymous.status_code == 403


def test_report_does_not_change_the_review_or_the_payment():
    assignment = make_assignment(now=timezone.now(), starts_in_hours=48)
    vacancy = assignment.vacancy
    now = timezone.now()
    vacancy.starts_at = now - timedelta(hours=5)
    vacancy.ends_at = now - timedelta(hours=1)
    vacancy.save()
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=vacancy.starts_at)
    assignments.check_out(assignment, now=vacancy.ends_at)
    assignment.refresh_from_db()
    report(company_user(vacancy.company), assignment.pk)

    assignments.approve_hours(assignment)
    assignment.refresh_from_db()
    assignments.settle(assignment)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.PAID
    assert LedgerEntry.objects.filter(assignment=assignment, kind="REPASSE_PRESTADOR").exists()
