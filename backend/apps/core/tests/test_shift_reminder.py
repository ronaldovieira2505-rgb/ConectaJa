"""US49 — lembrete do turno ao prestador, com endereço e link do mapa."""

from datetime import timedelta

import pytest
from django.urls import reverse

from apps.core.admin import PlatformParametersForm
from apps.core.deadlines import process_deadlines
from apps.core.models import Notification, PlatformParameters, PlatformParametersChange
from apps.core.notifications import notify_once
from apps.core.tests.factories import LAT, LNG, NOW, make_admin, make_assignment, make_worker
from apps.vacancies import assignment_services as assignments

pytestmark = pytest.mark.django_db

ADDRESS = {
    "street": "Praça da Sé",
    "number": "111",
    "district": "Sé",
    "city": "São Paulo",
    "state": "SP",
}


def reminders():
    return Notification.objects.filter(kind="LEMBRETE_TURNO")


def confirmed(**kw):
    """Alocação CONFIRMADA; o turno começa em 03/11/2026 às 09:00 (São Paulo)."""
    return make_assignment(title="Carga no Centro", **ADDRESS, **kw)


def test_reminder_inside_window_has_shift_address_map_and_checkin_time():
    assignment = confirmed()
    start = assignment.vacancy.starts_at

    done = process_deadlines(now=start - timedelta(hours=23))

    assert done["lembretes"] == 1
    reminder = reminders().get()
    assert reminder.user == assignment.worker.user
    assert reminder.title == "Lembrete: seu turno é amanhã"
    company = assignment.vacancy.company
    for text in (
        "Carga no Centro",
        company.trade_name or company.legal_name,
        "03/11/2026, das 09:00 às 13:00",
        "Endereço: Praça da Sé, 111 · Sé · São Paulo/SP.",
        "O check-in abre às 08:30.",
        "Ver no mapa: https://www.openstreetmap.org/?mlat=-23.550520&mlon=-46.633308",
    ):
        assert text in reminder.message
    assert reminder.link == f"/vagas/{assignment.vacancy.pk}"


def test_running_again_does_not_send_twice():
    assignment = confirmed()
    start = assignment.vacancy.starts_at

    process_deadlines(now=start - timedelta(hours=23))
    second = process_deadlines(now=start - timedelta(hours=23))
    process_deadlines(now=start - timedelta(hours=2))

    assert "lembretes" not in second
    assert reminders().count() == 1


def test_nothing_is_sent_before_the_window_opens():
    assignment = confirmed()

    process_deadlines(now=assignment.vacancy.starts_at - timedelta(hours=25))

    assert not reminders().exists()


def test_assignment_approved_inside_the_window_is_reminded_on_next_run():
    assignment = confirmed()

    done = process_deadlines(now=assignment.vacancy.starts_at - timedelta(hours=3))

    assert done["lembretes"] == 1
    assert reminders().get().title == "Lembrete: seu turno é hoje"


def test_cancelled_assignment_gets_no_reminder():
    assignment = confirmed()
    assignments.cancel_by_worker(assignment, now=NOW)

    process_deadlines(now=assignment.vacancy.starts_at - timedelta(hours=23))

    assert not reminders().exists()


def test_started_assignment_gets_no_reminder():
    assignment = confirmed()
    start = assignment.vacancy.starts_at
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start - timedelta(minutes=20))

    process_deadlines(now=start - timedelta(minutes=10))

    assert not reminders().exists()


def test_no_show_gets_no_reminder():
    assignment = confirmed()
    start = assignment.vacancy.starts_at

    process_deadlines(now=start + timedelta(minutes=31))

    assignment.refresh_from_db()
    assert assignment.status == "FALTA"
    assert not reminders().exists()


def test_window_follows_platform_parameter():
    assignment = confirmed()
    params = PlatformParameters.get()
    params.shift_reminder_minutes_before = 2880
    params.save()

    process_deadlines(now=assignment.vacancy.starts_at - timedelta(hours=47))

    assert reminders().get().title == "Lembrete: seu turno é em 03/11"


def test_notify_once_refuses_a_repeated_key():
    user = make_worker().user

    assert notify_once(user, "chave-1", "TESTE", "Primeiro") is True
    assert notify_once(user, "chave-1", "TESTE", "Segundo") is False
    assert Notification.objects.filter(dedup_key="chave-1").count() == 1


def admin_payload(**overrides):
    form = PlatformParametersForm(instance=PlatformParameters.get())
    data = {name: form.initial.get(name, getattr(form.instance, name)) for name in form.fields}
    data.update(overrides)
    return data


def test_admin_changes_the_parameter_and_the_change_is_audited(client):
    staff = make_admin()
    client.force_login(staff)
    url = reverse("admin:core_platformparameters_change", args=[1])

    page = client.get(url).content.decode().lower()
    response = client.post(url, admin_payload(shift_reminder_minutes_before=720))

    assert "lembrete do turno ao prestador (min antes do início)" in page
    assert response.status_code == 302
    assert PlatformParameters.get().shift_reminder_minutes_before == 720
    change = PlatformParametersChange.objects.get(field="shift_reminder_minutes_before")
    assert (change.old_value, change.new_value, change.changed_by) == ("1440", "720", staff)


def test_admin_rejects_zero(client):
    client.force_login(make_admin())
    url = reverse("admin:core_platformparameters_change", args=[1])

    response = client.post(url, admin_payload(shift_reminder_minutes_before=0))

    assert response.status_code == 200
    assert PlatformParameters.get().shift_reminder_minutes_before == 1440
