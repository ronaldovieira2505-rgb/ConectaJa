"""US61 — extrato dos ganhos do prestador em CSV."""

import csv
import io
from datetime import date, datetime, timedelta, timezone

import pytest
from rest_framework.test import APIClient

from apps.core.tests.factories import LAT, LNG, make_assignment, make_company, make_worker
from apps.payments.statement import parse_period
from apps.payments.wallet import wallet_for
from apps.vacancies import assignment_services as assignments

pytestmark = pytest.mark.django_db

URL = "/api/workers/me/statement.csv"
HEADER = [
    "Data do turno",
    "Empresa",
    "Vaga",
    "Valor do turno",
    "Taxa da plataforma",
    "Valor recebido",
    "Data do pagamento",
]


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def paid_shift(worker, paid_at, starts_in_hours=48, **kw):
    """Turno pago (`PAGA`) com o repasse lançado em `paid_at`."""
    assignment = make_assignment(worker=worker, starts_in_hours=starts_in_hours, **kw)
    start = assignment.vacancy.starts_at
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)
    assignments.check_out(assignment, now=start + timedelta(hours=4))
    assignments.approve_hours(assignment, now=start + timedelta(hours=5))
    return assignments.settle(assignment, now=paid_at)


def download(worker, **params):
    return client_for(worker.user).get(URL, params)


def parse(response):
    text = response.content.decode("utf-8")
    assert text.startswith("﻿"), "o arquivo precisa do BOM para o Excel"
    return list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))


# 03/11/2026 17:00 em São Paulo.
PAID_AT = datetime(2026, 11, 3, 20, 0, tzinfo=timezone.utc)


def test_csv_has_one_line_per_paid_shift_with_brazilian_values_and_total():
    worker = make_worker()
    assignment = paid_shift(worker, PAID_AT, title="Carga no Centro")

    response = download(worker, **{"from": "2026-11-01", "to": "2026-11-30"})

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    disposition = 'attachment; filename="extrato-conecta-ja-2026-11.csv"'
    assert response["Content-Disposition"] == disposition
    header, line, total = parse(response)
    assert header == HEADER
    company = assignment.vacancy.company
    assert line == [
        "03/11/2026",
        company.trade_name or company.legal_name,
        "Carga no Centro",
        "100,00",
        "3,00",
        "97,00",
        "03/11/2026",
    ]
    assert total == ["Total", "", "", "100,00", "3,00", "97,00", ""]


def test_totals_match_the_wallet_and_the_ledger():
    worker = make_worker()
    paid_shift(worker, PAID_AT, pay_per_person_cents=10000)
    paid_shift(worker, PAID_AT + timedelta(days=1), starts_in_hours=72, pay_per_person_cents=12350)

    rows = parse(download(worker, **{"from": "2026-11-01", "to": "2026-11-30"}))

    totals = wallet_for(worker)["totals"]
    assert len(rows) == 4  # cabeçalho, 2 turnos e total
    assert rows[-1][3:6] == ["223,50", "6,71", "216,79"]
    assert rows[-1][5] == f"{totals['released_cents'] // 100},{totals['released_cents'] % 100:02d}"
    assert rows[-1][4] == f"{totals['fees_cents'] // 100},{totals['fees_cents'] % 100:02d}"


def test_period_without_paid_shifts_returns_header_and_zero_total():
    worker = make_worker()
    paid_shift(worker, PAID_AT)

    rows = parse(download(worker, **{"from": "2026-10-01", "to": "2026-10-31"}))

    assert rows == [HEADER, ["Total", "", "", "0,00", "0,00", "0,00", ""]]


def test_period_is_cut_by_payment_date_in_sao_paulo_time():
    worker = make_worker()
    # 01/12 01:30 UTC ainda é 30/11 22:30 em São Paulo.
    paid_shift(worker, datetime(2026, 12, 1, 1, 30, tzinfo=timezone.utc))

    november = parse(download(worker, **{"from": "2026-11-01", "to": "2026-11-30"}))
    december = parse(download(worker, **{"from": "2026-12-01", "to": "2026-12-31"}))

    assert len(november) == 3
    assert november[1][6] == "30/11/2026"
    assert len(december) == 2


def test_only_the_workers_own_payouts_appear():
    worker, other = make_worker(), make_worker()
    paid_shift(other, PAID_AT)

    rows = parse(download(worker, **{"from": "2026-11-01", "to": "2026-11-30"}))

    assert rows == [HEADER, ["Total", "", "", "0,00", "0,00", "0,00", ""]]


def test_text_from_companies_never_becomes_a_spreadsheet_formula():
    worker = make_worker()
    paid_shift(worker, PAID_AT, title='=HYPERLINK("http://golpe.example")')

    rows = parse(download(worker, **{"from": "2026-11-01", "to": "2026-11-30"}))

    assert rows[1][2] == "'=HYPERLINK(\"http://golpe.example\")"


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"from": "2026-11-30", "to": "2026-11-01"}, "A data inicial não pode ser depois"),
        ({"from": "2025-01-01", "to": "2026-01-02"}, "no máximo 366 dias"),
        ({"from": "30/11/2026", "to": "2026-12-01"}, "Data inválida"),
        ({"from": "2026-11-01"}, "Informe a data inicial e a data final"),
    ],
)
def test_invalid_period_returns_clear_error(params, message):
    worker = make_worker()

    response = download(worker, **params)

    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_period_of_exactly_366_days_is_accepted():
    assert parse_period("2024-01-01", "2024-12-31") == (date(2024, 1, 1), date(2024, 12, 31))


def test_without_dates_the_period_is_the_current_month():
    assert parse_period(None, None, today=date(2026, 11, 20)) == (
        date(2026, 11, 1),
        date(2026, 11, 20),
    )


def test_company_and_visitor_cannot_download():
    company_user = make_company().members.first().user

    assert client_for(company_user).get(URL).status_code == 403
    assert APIClient().get(URL).status_code == 403
