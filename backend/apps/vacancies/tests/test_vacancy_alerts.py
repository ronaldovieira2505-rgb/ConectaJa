"""US19 — alerta quando surge uma vaga compatível perto de mim."""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Notification
from apps.core.tests.factories import LAT, LNG, make_assignment, make_company, make_worker
from apps.vacancies import alerts
from apps.vacancies import services as vacancies
from apps.vacancies.models import Vacancy
from apps.vacancies.tests.test_vacancy_api import create, login_as
from apps.workers.availability import DAYS, period_of

pytestmark = pytest.mark.django_db

# ~1,1 km ao norte da Praça da Sé (ponto padrão das vagas dos testes).
NEAR = (LAT + 0.01, LNG)
# ~33 km de distância.
FAR = (LAT + 0.3, LNG)


def alerted(**kw):
    home = kw.pop("home", NEAR)
    return make_worker(
        alerts_enabled=True,
        alert_radius_km=kw.pop("radius", 10),
        home_latitude=home[0],
        home_longitude=home[1],
        **kw,
    )


def publish(callbacks, **overrides):
    """Cria e paga uma vaga pela API, executando o que roda depois do commit."""
    client = login_as(make_company())
    vacancy_id = create(client, **overrides).data["id"]
    with callbacks(execute=True):
        client.post(f"/api/vacancies/{vacancy_id}/pay/")
    return Vacancy.objects.get(pk=vacancy_id)


def alerts_for(worker):
    return Notification.objects.filter(user=worker.user, kind="ALERTA_VAGA")


def test_worker_gets_an_alert_with_title_net_value_date_and_distance(
    django_capture_on_commit_callbacks,
):
    worker = alerted(skills=["CARGA_DESCARGA"])

    vacancy = publish(django_capture_on_commit_callbacks, title="Carga no Centro")

    note = alerts_for(worker).get()
    assert note.title == "Nova vaga perto de você"
    assert "Carga no Centro" in note.message
    assert "você recebe R$ 97,00" in note.message
    assert "1,1 km de casa" in note.message
    assert note.link == f"/vagas/{vacancy.pk}"


def test_outside_the_radius_or_other_category_gets_no_alert(django_capture_on_commit_callbacks):
    far = alerted(home=FAR)
    other_category = alerted(skills=["FOTOGRAFIA"])

    publish(django_capture_on_commit_callbacks)

    assert not alerts_for(far).exists()
    assert not alerts_for(other_category).exists()


def test_without_categories_every_category_counts(django_capture_on_commit_callbacks):
    worker = alerted()

    publish(django_capture_on_commit_callbacks, category="EVENTOS")

    assert alerts_for(worker).count() == 1


def test_only_my_schedule_uses_the_availability(django_capture_on_commit_callbacks):
    starts = timezone.now() + timedelta(hours=48)  # início padrão das vagas dos testes
    local = starts.astimezone(alerts.LOCAL_TZ)
    day = DAYS[local.weekday()]
    other_day = DAYS[(local.weekday() + 1) % 7]
    fits = alerted(
        availability_days=[day],
        availability_periods=[period_of(local.hour)],
        alert_only_my_schedule=True,
    )
    does_not_fit = alerted(
        availability_days=[other_day],
        availability_periods=[period_of(local.hour)],
        alert_only_my_schedule=True,
    )

    publish(
        django_capture_on_commit_callbacks,
        starts_at=starts.isoformat(),
        ends_at=(starts + timedelta(hours=4)).isoformat(),
    )

    assert alerts_for(fits).count() == 1
    assert not alerts_for(does_not_fit).exists()


def test_suspended_without_pix_or_busy_workers_get_no_alert(django_capture_on_commit_callbacks):
    suspended = alerted(suspension_indefinite=True)
    without_pix = alerted()
    without_pix.pix_key = ""
    without_pix.save(update_fields=["pix_key"])
    busy = alerted()
    start = timezone.now() + timedelta(hours=48)
    other = vacancies.create_vacancy(
        company=make_company(),
        title="Outro turno",
        category="OUTROS",
        description="x",
        latitude=LAT,
        longitude=LNG,
        starts_at=start,
        ends_at=start + timedelta(hours=4),
        pay_per_person_cents=10000,
        positions=1,
    )
    with django_capture_on_commit_callbacks(execute=False):
        vacancies.pay_vacancy(other)
    make_assignment(vacancy=other, worker=busy, now=timezone.now())

    publish(django_capture_on_commit_callbacks)

    for worker in (suspended, without_pix, busy):
        assert not alerts_for(worker).exists()


def test_one_alert_per_vacancy_and_at_most_five_per_day(django_capture_on_commit_callbacks):
    worker = alerted()
    for _ in range(6):
        publish(django_capture_on_commit_callbacks)
    vacancy = Vacancy.objects.latest("pk")

    alerts.send_vacancy_alerts(vacancy.pk)  # de novo, para a mesma vaga

    assert alerts_for(worker).count() == 5


def test_disabled_alerts_send_nothing(django_capture_on_commit_callbacks):
    worker = alerted()
    worker.alerts_enabled = False
    worker.save(update_fields=["alerts_enabled"])

    publish(django_capture_on_commit_callbacks)

    assert not alerts_for(worker).exists()


def test_a_failing_alert_never_undoes_the_payment(django_capture_on_commit_callbacks):
    alerted()
    with mock.patch.object(alerts, "send_vacancy_alerts", side_effect=RuntimeError("fora")):
        vacancy = publish(django_capture_on_commit_callbacks)

    assert vacancy.status == Vacancy.Status.PUBLISHED


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def test_worker_turns_alerts_on_with_home_location_and_radius():
    worker = make_worker()
    client = client_for(worker.user)

    refused = client.patch("/api/workers/me/", {"alerts_enabled": True}, format="json")
    saved = client.patch(
        "/api/workers/me/",
        {
            "home_latitude": "-23.540000",
            "home_longitude": "-46.630000",
            "alerts_enabled": True,
            "alert_radius_km": 20,
        },
        format="json",
    )

    assert refused.status_code == 400
    assert "localização de casa" in refused.json()["detail"]
    assert saved.status_code == 200
    assert saved.json()["alerts"] == {
        "enabled": True,
        "radius_km": 20,
        "only_my_schedule": False,
        "has_home_location": True,
    }
    assert "-23.54" not in saved.content.decode()  # a localização de casa não sai em claro


def test_radius_must_be_one_of_the_options():
    worker = make_worker(home_latitude=LAT, home_longitude=LNG)

    response = client_for(worker.user).patch(
        "/api/workers/me/", {"alert_radius_km": 15}, format="json"
    )

    assert response.status_code == 400
