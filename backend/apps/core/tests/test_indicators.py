from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.indicators import (
    compute_indicators,
    format_money,
    format_percent,
    percent,
)
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
from apps.vacancies import assignment_services as assignments
from apps.vacancies import services as vacancies

pytestmark = pytest.mark.django_db

START, END = date(2026, 10, 30), date(2026, 11, 2)
LATER = NOW + timedelta(days=10)  # todos os turnos já começaram


def pay_assignment(assignment):
    start = assignment.vacancy.starts_at
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)
    assignments.check_out(assignment, now=start + timedelta(hours=4))
    assignments.approve_hours(assignment, now=start + timedelta(hours=5))
    return assignments.settle(assignment, now=start + timedelta(hours=5))


@pytest.fixture
def known_data():
    """Duas vagas publicadas no período, uma sem pagamento e uma publicada fora dele.

    Carga (3 posições): 1 paga, 1 falta, 1 ainda confirmada.
    Limpeza (3 posições): 1 paga, 1 cancelada pela empresa (estornada), 1 posição livre.
    """
    company = make_company()
    loading = make_published_vacancy(company=company, positions=3, category="CARGA_DESCARGA")
    paid_loading = make_assignment(vacancy=loading)
    no_show = make_assignment(vacancy=loading)
    make_assignment(vacancy=loading)
    pay_assignment(paid_loading)
    assignments.mark_no_show(no_show, now=loading.starts_at + timedelta(hours=1))

    cleaning = make_published_vacancy(company=company, positions=3, category="LIMPEZA")
    paid_cleaning = make_assignment(vacancy=cleaning)
    cancelled = make_assignment(vacancy=cleaning)
    pay_assignment(paid_cleaning)
    assignments.cancel_confirmed_by_company(cancelled, reason="Mudança de planos", now=NOW)

    # Fora da conta: vaga criada mas não paga, e vaga publicada 60 dias antes.
    vacancies.create_vacancy(
        company=company,
        now=NOW,
        **{
            "title": "Sem pagamento",
            "category": "VAREJO",
            "description": "x",
            "latitude": LAT,
            "longitude": LNG,
            "starts_at": NOW + timedelta(hours=48),
            "ends_at": NOW + timedelta(hours=52),
            "pay_per_person_cents": 10000,
            "positions": 5,
        },
    )
    old = NOW - timedelta(days=60)
    make_assignment(vacancy=make_published_vacancy(company=company, now=old, positions=4), now=old)


def test_percent_helpers():
    assert percent(1, 3) == Decimal("33.3")
    assert percent(0, 5) == Decimal("0.0")
    assert percent(1, 0) is None
    assert format_percent(Decimal("83.3")) == "83,3%"
    assert format_percent(None) == "—"
    assert format_money(1234567) == "R$ 12.345,67"
    assert format_money(5) == "R$ 0,05"


def test_overall_indicators_match_known_data(known_data):
    overall, _ = compute_indicators(START, END, now=LATER)

    assert overall.published_vacancies == 2
    assert overall.positions == 6
    assert overall.filled_positions == 5
    assert overall.fill_rate == Decimal("83.3")  # 5 / 6
    assert overall.reached_start == 4  # a cancelada pela empresa não conta
    assert overall.no_shows == 1
    assert overall.no_show_rate == Decimal("25.0")  # 1 / 4
    assert overall.paid_shifts == 2
    assert overall.platform_fee_cents == 600  # 3% de 2 x R$ 100
    assert overall.gross_moved_cents == 20000  # 2 x (R$ 97 + R$ 3)
    assert overall.refund_count == 1
    assert overall.refund_cents == 10000


def test_indicators_by_category(known_data):
    _, by_category = compute_indicators(START, END, now=LATER)
    rows = {label: row for label, row in by_category}

    loading = rows["Carga e descarga"]
    assert (loading.published_vacancies, loading.positions, loading.filled_positions) == (1, 3, 3)
    assert loading.fill_rate == Decimal("100.0")
    assert (loading.reached_start, loading.no_shows) == (3, 1)
    assert loading.no_show_rate == Decimal("33.3")
    assert (loading.paid_shifts, loading.platform_fee_cents) == (1, 300)
    assert loading.refund_count == 0

    cleaning = rows["Limpeza"]
    assert (cleaning.positions, cleaning.filled_positions) == (3, 2)
    assert cleaning.fill_rate == Decimal("66.7")
    assert (cleaning.reached_start, cleaning.no_shows) == (1, 0)
    assert cleaning.no_show_rate == Decimal("0.0")
    assert (cleaning.refund_count, cleaning.refund_cents) == (1, 10000)

    retail = rows["Varejo"]
    assert retail.positions == 0
    assert retail.fill_rate is None
    assert retail.no_show_rate is None


def test_category_filter(known_data):
    overall, by_category = compute_indicators(START, END, category="LIMPEZA", now=LATER)

    assert overall.positions == 3
    assert overall.fill_rate == Decimal("66.7")
    assert [label for label, _ in by_category] == ["Limpeza"]


def test_no_show_rate_ignores_shifts_that_have_not_started(known_data):
    overall, _ = compute_indicators(START, END, now=NOW)  # nenhum turno começou

    assert overall.reached_start == 0
    assert overall.no_show_rate is None


def test_period_without_data_has_no_rates(known_data):
    overall, by_category = compute_indicators(date(2025, 1, 1), date(2025, 1, 31), now=LATER)

    assert overall.published_vacancies == 0
    assert overall.fill_rate is None and overall.no_show_rate is None
    assert all(row.fill_rate is None for _, row in by_category)


@pytest.fixture
def admin_client(client):
    client.force_login(make_admin())
    return client


def test_admin_sees_indicators_page(admin_client, known_data):
    response = admin_client.get(
        reverse("admin:indicators"), {"inicio": "2026-10-30", "fim": "2026-11-02"}
    )

    assert response.status_code == 200
    assert response.context["overall"].positions == 6
    assert "83,3%" in response.content.decode()


def test_empty_period_shows_dash_instead_of_error(admin_client):
    response = admin_client.get(reverse("admin:indicators"))

    assert response.status_code == 200
    content = response.content.decode()
    assert 'class="fill-rate">—<' in content
    assert 'class="no-show-rate">—<' in content


def test_invalid_filters_are_reported(admin_client):
    response = admin_client.get(
        reverse("admin:indicators"), {"inicio": "x", "categoria": "INEXISTENTE"}
    )

    assert response.status_code == 200
    assert response.context["errors"]


def test_anonymous_cannot_access(client):
    response = client.get(reverse("admin:indicators"))

    assert response.status_code == 302
    assert "login" in response["Location"]


@pytest.mark.parametrize("role", [Role.COMPANY, Role.WORKER])
def test_non_admin_roles_are_denied(client, role):
    client.force_login(make_user(role, is_staff=True))

    assert client.get(reverse("admin:indicators")).status_code == 403
