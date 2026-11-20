"""US10 — dias e horários em que o prestador está disponível."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.tests.factories import NOW, make_published_vacancy, make_worker
from apps.vacancies import application_services as applications
from apps.workers.availability import summary

pytestmark = pytest.mark.django_db

URL = "/api/workers/me/"
SP = ZoneInfo("America/Sao_Paulo")


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def next_weekday(weekday, hour):
    """Próxima data (a partir de amanhã + 1) no dia da semana e hora de São Paulo."""
    day = timezone.localdate() + timedelta(days=2)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, tzinfo=SP)


def test_worker_saves_days_and_periods_and_sees_the_summary():
    worker = make_worker()
    client = client_for(worker.user)

    response = client.patch(
        URL,
        {
            "availability_days": ["SEX", "SEG", "TER", "QUA", "QUI"],
            "availability_periods": ["TARDE", "MANHA"],
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["availability"] == {
        "days": ["SEG", "TER", "QUA", "QUI", "SEX"],
        "periods": ["MANHA", "TARDE"],
        "summary": "Seg–Sex · manhã e tarde",
    }


@pytest.mark.parametrize(
    ("days", "periods", "text"),
    [
        (["SEG", "QUA", "SEX"], ["NOITE"], "Seg, Qua, Sex · noite"),
        (
            ["SEG", "TER", "QUA", "SAB"],
            ["MANHA", "TARDE", "NOITE"],
            "Seg–Qua, Sáb · manhã, tarde e noite",
        ),
        (["SAB", "DOM"], ["MANHA"], "Sáb, Dom · manhã"),
        ([], ["MANHA"], ""),
    ],
)
def test_summary_text(days, periods, text):
    worker = make_worker(availability_days=days, availability_periods=periods)

    assert summary(worker) == text


@pytest.mark.parametrize(
    "payload",
    [
        {"availability_days": ["SEG", "SEG"]},
        {"availability_days": ["SEGUNDA"]},
        {"availability_periods": ["MADRUGADA"]},
        {"availability_periods": "MANHA"},
    ],
)
def test_invalid_values_are_refused_and_nothing_changes(payload):
    worker = make_worker()

    response = client_for(worker.user).patch(URL, payload, format="json")

    assert response.status_code == 400
    worker.refresh_from_db()
    assert (worker.availability_days, worker.availability_periods) == ([], [])


def test_an_invalid_field_rolls_back_the_others():
    worker = make_worker()

    response = client_for(worker.user).patch(
        URL, {"bio": "Pintor há 5 anos.", "availability_days": ["XYZ"]}, format="json"
    )

    assert response.status_code == 400
    worker.refresh_from_db()
    assert worker.bio == ""


def search_ids(client, **params):
    return [v["id"] for v in client.get("/api/vacancies/", params).json()["results"]]


def test_my_schedule_filter_keeps_only_vacancies_in_the_marked_day_and_period():
    worker = make_worker(availability_days=["SEG"], availability_periods=["MANHA"])
    client = client_for(worker.user)
    now = timezone.now()
    monday_morning = next_weekday(0, 9)
    monday_evening = next_weekday(0, 19)
    tuesday_morning = next_weekday(1, 9)
    fit = make_published_vacancy(
        now=now, starts_in_hours=(monday_morning - now).total_seconds() / 3600
    )
    late = make_published_vacancy(
        now=now, starts_in_hours=(monday_evening - now).total_seconds() / 3600
    )
    other_day = make_published_vacancy(
        now=now, starts_in_hours=(tuesday_morning - now).total_seconds() / 3600
    )

    all_ids = search_ids(client)
    mine = search_ids(client, my_schedule="1")

    assert {fit.pk, late.pk, other_day.pk} <= set(all_ids)
    assert mine == [fit.pk]
    assert client.get("/api/vacancies/").json()["my_schedule_available"] is True


def test_without_availability_the_filter_is_ignored_and_not_offered():
    worker = make_worker()
    client = client_for(worker.user)
    vacancy = make_published_vacancy(now=timezone.now())

    data = client.get("/api/vacancies/", {"my_schedule": "1"}).json()

    assert vacancy.pk in [v["id"] for v in data["results"]]
    assert data["my_schedule_available"] is False


def test_availability_is_only_informative_and_does_not_block_applying():
    worker = make_worker(availability_days=["DOM"], availability_periods=["NOITE"])
    vacancy = make_published_vacancy()

    application = applications.apply_to_vacancy(vacancy, worker, now=NOW)

    assert application.pk


def test_company_sees_the_summary_in_the_candidate_list():
    worker = make_worker(
        availability_days=["SEG", "TER", "QUA", "QUI", "SEX"],
        availability_periods=["MANHA", "TARDE"],
    )
    vacancy = make_published_vacancy()
    applications.apply_to_vacancy(vacancy, worker, now=NOW)
    company_user = vacancy.company.members.first().user

    candidate = (
        client_for(company_user)
        .get(f"/api/vacancies/{vacancy.pk}/candidates/")
        .json()["candidates"][0]
    )

    assert candidate["availability_summary"] == "Seg–Sex · manhã e tarde"
