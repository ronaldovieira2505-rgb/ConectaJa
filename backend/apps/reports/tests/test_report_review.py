"""US74: o admin analisa as denúncias recebidas."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.core.models import Notification, StateTransition
from apps.core.tests.factories import (
    make_admin,
    make_assignment,
    make_company,
    make_published_vacancy,
    make_user,
    make_worker,
)
from apps.reports import review, services
from apps.reports.models import Report
from apps.vacancies.models import Assignment

pytestmark = pytest.mark.django_db

R = Report.Status
DESCRIPTION = "Pediram um PIX adiantado para garantir a vaga."


def company_report(reporter=None, company=None):
    reporter = reporter or make_worker()
    company = company or make_company()
    return services.report_vacancy_or_company(
        reporter.user,
        target_type="EMPRESA",
        target_id=company.pk,
        reason="PAGAMENTO_POR_FORA",
        description=DESCRIPTION,
    )


def worker_report(assignment=None):
    assignment = assignment or make_assignment(now=timezone.now(), starts_in_hours=48)
    company = assignment.vacancy.company
    return services.report_worker(
        company.members.first().user,
        company,
        assignment_id=assignment.pk,
        reason="DANO_FURTO",
        description="Sumiram duas caixas do estoque.",
    )


def review_url(report):
    return reverse("admin:reports_report_review", args=[report.pk])


@pytest.fixture
def admin_client(client):
    admin = make_admin()
    client.force_login(admin)
    client.admin = admin
    return client


# Transições ---------------------------------------------------------------------------------


def test_admin_marks_report_as_in_review_and_it_is_audited(admin_client):
    report = company_report()
    response = admin_client.post(review_url(report), {"action": "start"})
    assert response.status_code == 302
    report.refresh_from_db()
    assert report.status == R.REVIEWING
    assert StateTransition.objects.filter(
        entity_type="Report",
        entity_id=report.pk,
        from_state=R.OPEN,
        to_state=R.REVIEWING,
        actor=admin_client.admin,
    ).exists()


def test_conclude_upheld_with_decision_notifies_reporter_without_details(admin_client):
    report = company_report()
    response = admin_client.post(
        review_url(report),
        {"action": "conclude", "result": "procedente", "decision": "Prints confirmam o golpe."},
    )
    assert response.status_code == 302
    report.refresh_from_db()
    assert report.status == R.UPHELD
    assert report.decision == "Prints confirmam o golpe."
    assert report.decided_by == admin_client.admin
    assert report.decided_at is not None
    assert StateTransition.objects.filter(
        entity_type="Report",
        entity_id=report.pk,
        to_state=R.UPHELD,
        actor=admin_client.admin,
        reason="Prints confirmam o golpe.",
    ).exists()

    note = Notification.objects.get(user=report.reporter, title="Sua denúncia foi analisada")
    assert "procedente" in note.message
    assert "Prints" not in note.message  # o parecer não vai para quem denunciou
    assert str(report.company) not in note.message
    company_users = [m.user for m in report.company.members.all()]
    assert not Notification.objects.filter(user__in=company_users, kind="DENUNCIA").exists()


def test_conclude_dismissed_from_review(admin_client):
    report = company_report()
    review.start_review(report, actor=admin_client.admin)
    admin_client.post(
        review_url(report),
        {"action": "conclude", "result": "improcedente", "decision": "Sem provas do ocorrido."},
    )
    report.refresh_from_db()
    assert report.status == R.DISMISSED
    note = Notification.objects.get(user=report.reporter, title="Sua denúncia foi analisada")
    assert "improcedente" in note.message


@pytest.mark.parametrize("decision", ["", "   "])
def test_decision_is_required(admin_client, decision):
    report = company_report()
    response = admin_client.post(
        review_url(report), {"action": "conclude", "result": "procedente", "decision": decision}
    )
    assert response.status_code == 200
    assert "O parecer é obrigatório." in response.content.decode()
    report.refresh_from_db()
    assert report.status == R.OPEN
    with pytest.raises(DomainError, match="parecer"):
        review.conclude(report, actor=admin_client.admin, upheld=True, decision=decision)


def test_concluded_report_cannot_change_again():
    admin = make_admin()
    report = company_report()
    review.conclude(report, actor=admin, upheld=False, decision="Sem provas.")
    with pytest.raises(DomainError, match="já foi concluída"):
        review.conclude(report, actor=admin, upheld=True, decision="Mudei de ideia.")
    with pytest.raises(DomainError):
        review.start_review(report, actor=admin)


def test_only_admin_reviews():
    report = company_report()
    staff = make_user(Role.COMPANY, is_staff=True)
    with pytest.raises(review.ReviewNotAllowed):
        review.start_review(report, actor=staff)
    with pytest.raises(review.ReviewNotAllowed):
        review.conclude(report, actor=staff, upheld=True, decision="x" * 20)


def test_review_screen_is_admin_only(client):
    report = company_report()
    assert client.get(review_url(report)).status_code == 302  # login do admin
    staff = make_user(Role.COMPANY, is_staff=True, is_superuser=True)
    client.force_login(staff)
    assert client.get(review_url(report)).status_code == 403


# Suspensão na mesma tela --------------------------------------------------------------------


def test_upheld_can_suspend_the_reported_worker_in_the_same_screen(admin_client):
    report = worker_report()
    response = admin_client.post(
        review_url(report),
        {
            "action": "conclude",
            "result": "procedente",
            "decision": "Confirmado pelas câmeras.",
            "suspend": "on",
            "days": "15",
        },
    )
    assert response.status_code == 302
    worker = report.worker
    worker.refresh_from_db()
    assert worker.is_suspended(timezone.now())
    assert StateTransition.objects.filter(
        entity_type="WorkerSuspension", entity_id=worker.pk, actor=admin_client.admin
    ).exists()


def test_suspension_only_when_upheld(admin_client):
    report = company_report()
    response = admin_client.post(
        review_url(report),
        {
            "action": "conclude",
            "result": "improcedente",
            "decision": "Sem provas.",
            "suspend": "on",
            "indefinite": "on",
        },
    )
    assert response.status_code == 200
    report.refresh_from_db()
    assert report.status == R.OPEN
    assert not report.company.is_suspended(timezone.now())


def test_suspend_link_after_upheld(admin_client):
    report = company_report()
    review.conclude(report, actor=admin_client.admin, upheld=True, decision="Confirmado.")
    page = admin_client.get(review_url(report)).content.decode()
    suspend = reverse("admin:companies_company_suspend", args=[report.company_id])
    assert suspend in page


# Lista, detalhe e alerta --------------------------------------------------------------------


def test_list_shows_reporter_target_reason_status_and_highlights_old_open(admin_client):
    old = company_report()
    Report.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=49))
    recent = company_report()
    page = admin_client.get(reverse("admin:reports_report_changelist")).content.decode()
    assert "mais de 48 h" in page
    assert page.count("(mais de 48 h)") == 1
    assert "(prestador)" in page
    assert recent.target_label in page
    assert "Pedido de pagamento por fora" in page
    overdue = admin_client.get(
        reverse("admin:reports_report_changelist") + "?atrasadas=sim"
    ).content.decode()
    assert review_url(old) in overdue
    assert review_url(recent) not in overdue


def test_list_filters_by_status_target_and_reason(admin_client):
    company_report()
    worker_report()
    url = reverse("admin:reports_report_changelist")
    for query in ("?status__exact=ABERTA", "?target_type__exact=PRESTADOR", "?reason__exact=OUTRO"):
        assert admin_client.get(url + query).status_code == 200


def test_detail_shows_description_target_history_and_shift_history(admin_client):
    assignment = make_assignment(now=timezone.now(), starts_in_hours=48)
    previous = worker_report(assignment)
    review.conclude(previous, actor=admin_client.admin, upheld=True, decision="Confirmado.")
    other = make_assignment(
        vacancy=make_published_vacancy(now=timezone.now(), starts_in_hours=96),
        worker=assignment.worker,
        now=timezone.now(),
    )
    Assignment.objects.filter(pk=other.pk).update(status=Assignment.Status.NO_SHOW)
    report = worker_report(other)

    page = admin_client.get(review_url(report)).content.decode()
    assert "Sumiram duas caixas do estoque." in page
    assert "Faltas: 1" in page
    assert "Denúncias procedentes: 1" in page
    assert f"#{previous.pk}" in page
    history = reverse("admin:vacancies_vacancy_full_history", args=[other.vacancy_id])
    assert history in page


def test_alert_with_three_or_more_upheld_reports(admin_client):
    company = make_company()
    for _ in range(3):
        report = company_report(company=company)
        review.conclude(report, actor=admin_client.admin, upheld=True, decision="Confirmado.")
    assert review.has_upheld_alert(company)
    fourth = company_report(company=company)
    page = admin_client.get(review_url(fourth)).content.decode()
    assert "Este alvo tem 3 denúncias procedentes." in page

    profile = admin_client.get(
        reverse("admin:companies_company_change", args=[company.pk])
    ).content.decode()
    assert "⚠ 3" in profile


def test_two_upheld_reports_do_not_raise_the_alert():
    admin = make_admin()
    assignment = make_assignment(now=timezone.now(), starts_in_hours=48)
    for _ in range(2):
        report = worker_report(assignment)
        review.conclude(report, actor=admin, upheld=True, decision="Confirmado.")
    assert review.upheld_count(assignment.worker) == 2
    assert not review.has_upheld_alert(assignment.worker)
