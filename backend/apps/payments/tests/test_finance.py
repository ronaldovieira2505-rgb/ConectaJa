"""US77 — painel financeiro do admin: retido, repassado, taxa, estornado e saldo."""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.tests.factories import (
    LAT,
    LNG,
    NOW,
    make_admin,
    make_assignment,
    make_company,
    make_published_vacancy,
    make_user,
)
from apps.payments import services as payments
from apps.payments.finance import compute_finance, default_period, format_money
from apps.payments.models import Custody
from apps.vacancies import assignment_services as assignments

pytestmark = pytest.mark.django_db

START, END = date(2026, 10, 30), date(2026, 11, 2)


def pay_assignment(assignment):
    start = assignment.vacancy.starts_at
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)
    assignments.check_out(assignment, now=start + timedelta(hours=4))
    assignments.approve_hours(assignment, now=start + timedelta(hours=5))
    return assignments.settle(assignment, now=start + timedelta(hours=5))


@pytest.fixture
def known_data():
    """Empresa A: vaga de 3 posições (1 paga, 1 estornada, 1 ainda confirmada).
    Empresa B: vaga de 1 posição, paga e encerrada. Turnos de R$ 100,00."""
    company_a, company_b = make_company(), make_company()
    open_vacancy = make_published_vacancy(company=company_a, positions=3)
    paid = make_assignment(vacancy=open_vacancy)
    cancelled = make_assignment(vacancy=open_vacancy)
    make_assignment(vacancy=open_vacancy)
    pay_assignment(paid)
    assignments.cancel_confirmed_by_company(cancelled, reason="Mudança de planos", now=NOW)

    closed_vacancy = make_published_vacancy(company=company_b, positions=1)
    pay_assignment(make_assignment(vacancy=closed_vacancy))
    payments.close(closed_vacancy.custody, now=NOW)
    return company_a, company_b, open_vacancy, closed_vacancy


def test_totals_match_the_ledger(known_data):
    totals, rows = compute_finance(START, END)

    assert totals.retained_cents == 40000
    assert totals.paid_out_cents == 19400
    assert totals.fees_cents == 600
    assert totals.refunded_cents == 10000
    assert totals.balance_cents == 10000
    assert len(rows) == 2


def test_rows_per_vacancy(known_data):
    _, _, open_vacancy, closed_vacancy = known_data

    _, rows = compute_finance(START, END)

    by_vacancy = {row.vacancy.pk: row for row in rows}
    row = by_vacancy[open_vacancy.pk]
    assert (row.retained_cents, row.paid_out_cents, row.fees_cents) == (30000, 9700, 300)
    assert (row.refunded_cents, row.balance_cents) == (10000, 10000)
    assert row.status_display == "Retida"
    assert not row.diverged
    closed = by_vacancy[closed_vacancy.pk]
    assert closed.balance_cents == 0
    assert closed.custody.status == Custody.Status.CLOSED
    assert not closed.diverged


def test_company_filter_limits_totals_and_rows(known_data):
    company_a, _, open_vacancy, _ = known_data

    totals, rows = compute_finance(START, END, company_id=company_a.pk)

    assert [row.vacancy.pk for row in rows] == [open_vacancy.pk]
    assert totals.retained_cents == 30000
    assert totals.refunded_cents == 10000


def test_period_outside_the_retention_has_no_rows(known_data):
    totals, rows = compute_finance(date(2026, 9, 1), date(2026, 9, 30))

    assert rows == []
    assert totals.retained_cents == 0 and totals.balance_cents == 0


def test_closed_custody_that_does_not_add_up_is_a_divergence(known_data):
    vacancy = make_published_vacancy(company=known_data[0], positions=1)
    Custody.objects.filter(vacancy=vacancy).update(status=Custody.Status.CLOSED)

    _, rows = compute_finance(START, END)

    diverged = [row for row in rows if row.diverged]
    assert [row.vacancy.pk for row in diverged] == [vacancy.pk]


def test_money_format_and_default_period():
    assert format_money(1234567) == "R$ 12.345,67"
    assert format_money(5) == "R$ 0,05"
    start, end = default_period(NOW)
    assert (end - start).days == 30 and end == date(2026, 11, 1)


@pytest.fixture
def admin_client(client):
    client.force_login(make_admin())
    return client


def test_admin_sees_page_with_totals_and_history_link(admin_client, known_data):
    response = admin_client.get(
        reverse("admin:finance"), {"inicio": "2026-10-30", "fim": "2026-11-02"}
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert 'class="retained">R$ 400,00<' in content
    assert 'class="paid-out">R$ 194,00<' in content
    assert 'class="fees">R$ 6,00<' in content
    assert 'class="refunded">R$ 100,00<' in content
    assert 'class="balance">R$ 100,00<' in content
    vacancy = known_data[2]
    assert reverse("admin:vacancies_vacancy_full_history", args=[vacancy.pk]) in content
    assert "Divergência" not in content


def test_page_highlights_divergence(admin_client, known_data):
    vacancy = make_published_vacancy(company=known_data[0], positions=1)
    Custody.objects.filter(vacancy=vacancy).update(status=Custody.Status.CLOSED)

    response = admin_client.get(
        reverse("admin:finance"), {"inicio": "2026-10-30", "fim": "2026-11-02"}
    )

    assert "Divergência" in response.content.decode()


def test_page_filters_by_company(admin_client, known_data):
    company_b = known_data[1]

    response = admin_client.get(
        reverse("admin:finance"),
        {"inicio": "2026-10-30", "fim": "2026-11-02", "empresa": company_b.pk},
    )

    assert response.context["totals"].retained_cents == 10000
    assert len(response.context["rows"]) == 1


def test_empty_period_shows_message_without_error(admin_client):
    response = admin_client.get(reverse("admin:finance"))

    assert response.status_code == 200
    assert "Nenhum lançamento no período" in response.content.decode()


def test_invalid_filters_are_reported(admin_client):
    response = admin_client.get(reverse("admin:finance"), {"inicio": "x", "empresa": "999999"})

    assert response.status_code == 200
    assert response.context["errors"]


def test_anonymous_cannot_access(client):
    response = client.get(reverse("admin:finance"))

    assert response.status_code == 302
    assert "login" in response["Location"]


@pytest.mark.parametrize("role", [Role.COMPANY, Role.WORKER])
def test_non_admin_roles_are_denied(client, role):
    client.force_login(make_user(role, is_staff=True))

    assert client.get(reverse("admin:finance")).status_code == 403
