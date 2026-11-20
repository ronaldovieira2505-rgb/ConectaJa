"""US65: o prestador sobe (e cai) de nível conforme turnos pagos, nota, faltas e cancelamentos."""

from datetime import timedelta
from itertools import count

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Notification, PlatformParameters, StateTransition
from apps.core.tests.factories import (
    LAT,
    LNG,
    NOW,
    make_admin,
    make_assignment,
    make_published_vacancy,
    make_worker,
)
from apps.core.tests.test_shift_reminder import admin_payload
from apps.vacancies import application_services as applications
from apps.vacancies import assignment_services as assignments
from apps.vacancies import review_services
from apps.vacancies.models import Assignment, Review
from apps.workers import levels
from apps.workers.models import Worker

pytestmark = pytest.mark.django_db

L = Worker.Level
LATER = NOW + timedelta(days=1)
_slot = count(1)


def shift(worker, *, status=Assignment.Status.PAID, rating=None):
    """Turno do prestador em horários que não se sobrepõem (status ajustado direto no banco)."""
    vacancy = make_published_vacancy(now=NOW, starts_in_hours=24 + 12 * next(_slot))
    assignment = make_assignment(vacancy=vacancy, worker=worker, now=NOW)
    Assignment.objects.filter(pk=assignment.pk).update(status=status)
    if rating is not None:
        Review.objects.create(
            assignment=assignment,
            direction=Review.Direction.COMPANY_TO_WORKER,
            author=vacancy.company.members.first().user,
            rating=rating,
            created_at=NOW,
        )
    return assignment


def paid(worker, n, rating=None):
    return [shift(worker, rating=rating) for _ in range(n)]


def absence(worker, days_ago=10):
    """Falta registrada `days_ago` dias antes de LATER (como o `processar_prazos` grava)."""
    assignment = shift(worker, status=Assignment.Status.NO_SHOW)
    StateTransition.objects.create(
        entity_type="Assignment",
        entity_id=assignment.pk,
        from_state="CONFIRMADA",
        to_state="FALTA",
        reason="Sem check-in dentro da tolerância",
        created_at=LATER - timedelta(days=days_ago),
    )


def level_of(worker):
    return levels.compute(worker, now=LATER)[0]


def level_notes(worker):
    return list(
        Notification.objects.filter(user=worker.user, kind="NIVEL").values_list("title", flat=True)
    )


# Regras de cada nível -----------------------------------------------------------------------


def test_new_with_fewer_than_5_paid_shifts():
    worker = make_worker()
    paid(worker, 4, rating=5)
    assert level_of(worker) == L.NEW


def test_bronze_needs_5_paid_shifts_and_rating_4():
    worker = make_worker()
    paid(worker, 5, rating=4)
    assert level_of(worker) == L.BRONZE


def test_rating_below_4_or_no_reviews_is_not_bronze():
    low = make_worker()
    paid(low, 4, rating=4)
    paid(low, 1, rating=3)  # média 3,8
    assert level_of(low) == L.NEW
    unrated = make_worker()
    paid(unrated, 6)
    assert level_of(unrated) == L.NEW


def test_silver_needs_15_shifts_rating_4_5_and_no_absence_in_90_days():
    worker = make_worker()
    paid(worker, 15, rating=5)
    assert level_of(worker) == L.SILVER
    absence(worker, days_ago=10)
    assert level_of(worker) == L.BRONZE


def test_absence_older_than_90_days_does_not_count():
    worker = make_worker()
    paid(worker, 15, rating=5)
    absence(worker, days_ago=100)
    assert level_of(worker) == L.SILVER


def test_gold_needs_30_shifts_rating_4_7_and_no_absence_nor_late_cancel():
    worker = make_worker()
    paid(worker, 30, rating=5)
    assert level_of(worker) == L.GOLD
    paid(worker, 2, rating=3)  # média 4,875 → 4,9: ainda Ouro
    assert level_of(worker) == L.GOLD


def test_gold_with_rating_below_4_7_is_silver():
    worker = make_worker()
    paid(worker, 20, rating=5)
    paid(worker, 10, rating=4)  # média 4,67 → 4,7 exibido: ainda Ouro
    assert level_of(worker) == L.GOLD
    paid(worker, 2, rating=3)  # 4,5
    assert level_of(worker) == L.SILVER


def test_levels_use_platform_parameters():
    params = PlatformParameters.get()
    params.level_bronze_shifts = 3
    params.save()
    worker = make_worker()
    paid(worker, 3, rating=4)
    assert level_of(worker) == L.BRONZE


# Recálculo, notificações e idempotência -----------------------------------------------------


def test_going_up_notifies_once_and_is_audited():
    worker = make_worker()
    paid(worker, 5, rating=5)
    levels.recalculate(worker, reason="Turno pago", now=LATER)
    worker.refresh_from_db()
    assert worker.level == L.BRONZE
    assert level_notes(worker) == ["Parabéns, você subiu para o nível Bronze"]
    assert StateTransition.objects.filter(
        entity_type="WorkerLevel", entity_id=worker.pk, from_state=L.NEW, to_state=L.BRONZE
    ).exists()

    levels.recalculate(worker, reason="Turno pago", now=LATER)  # de novo: nada muda
    assert level_notes(worker) == ["Parabéns, você subiu para o nível Bronze"]
    assert StateTransition.objects.filter(entity_type="WorkerLevel").count() == 1


def test_absence_drops_the_level_with_the_reason():
    worker = make_worker()
    paid(worker, 15, rating=5)
    levels.recalculate(worker, now=LATER)
    worker.refresh_from_db()
    assert worker.level == L.SILVER

    absence(worker, days_ago=1)
    levels.recalculate(worker, reason="Falta registrada", now=LATER)
    worker.refresh_from_db()
    assert worker.level == L.BRONZE
    note = Notification.objects.filter(user=worker.user, kind="NIVEL").latest("pk")
    assert note.title == "Seu nível caiu para Bronze"
    assert "falta nos últimos 90 dias" in note.message


def test_late_cancel_drops_one_level_immediately():
    worker = make_worker()
    paid(worker, 15, rating=5)
    levels.recalculate(worker, now=NOW)
    worker.refresh_from_db()
    assert worker.level == L.SILVER

    # Turno começando em 2 h: cancelar agora é tardio.
    now = timezone.now()
    soon = make_assignment(
        vacancy=make_published_vacancy(now=now, starts_in_hours=20),
        worker=worker,
        now=now,
    )
    soon.vacancy.starts_at = now + timedelta(hours=2)
    soon.vacancy.ends_at = now + timedelta(hours=6)
    soon.vacancy.save()
    assignments.cancel_by_worker(soon, actor=worker.user, now=now)

    worker.refresh_from_db()
    assert worker.level == L.BRONZE  # Prata continua cumprida, mas cai um nível
    note = Notification.objects.filter(user=worker.user, kind="NIVEL").latest("pk")
    assert note.title == "Seu nível caiu para Bronze"
    assert "cancelamento tardio" in note.message


def test_gold_with_a_late_cancel_is_silver():
    worker = make_worker()
    paid(worker, 30, rating=5)
    assignment = shift(worker, status=Assignment.Status.CANCELLED_BY_WORKER)
    StateTransition.objects.create(
        entity_type="Assignment",
        entity_id=assignment.pk,
        from_state="CONFIRMADA",
        to_state="CANCELADA_PRESTADOR",
        reason="Cancelamento tardio",
        created_at=LATER - timedelta(days=5),
    )
    assert level_of(worker) == L.SILVER


# Gatilhos -------------------------------------------------------------------------------------


def test_paying_a_shift_recalculates():
    worker = make_worker()
    paid(worker, 4, rating=5)
    now = timezone.now()
    last = make_assignment(
        vacancy=make_published_vacancy(now=now, starts_in_hours=200), worker=worker, now=now
    )
    vacancy = last.vacancy
    vacancy.starts_at = now - timedelta(hours=5)
    vacancy.ends_at = now - timedelta(hours=1)
    vacancy.save()
    assignments.check_in(last, lat=LAT, lng=LNG, now=vacancy.starts_at)
    assignments.check_out(last, now=vacancy.ends_at)
    last.refresh_from_db()
    assignments.approve_hours(last)
    last.refresh_from_db()
    assignments.settle(last)
    worker.refresh_from_db()
    # 5 pagos, mas o 5º ainda sem nota: média 5,0 das 4 avaliações → Bronze.
    assert worker.level == L.BRONZE
    assert "Parabéns, você subiu para o nível Bronze" in level_notes(worker)


def test_review_recalculates():
    worker = make_worker()
    paid(worker, 5)  # 5 pagos, mas sem nota: continua Novo
    worker.refresh_from_db()
    assert worker.level == L.NEW
    approved = shift(worker, status=Assignment.Status.APPROVED)
    Assignment.objects.filter(pk=approved.pk).update(validated_at=timezone.now())
    target = Assignment.objects.get(pk=approved.pk)
    review_services.review_worker(
        target, author=target.vacancy.company.members.first().user, rating=5
    )
    worker.refresh_from_db()
    assert worker.level == L.BRONZE


def test_no_show_recalculates():
    worker = make_worker()
    paid(worker, 15, rating=5)
    levels.recalculate(worker, now=timezone.now())
    now = timezone.now()
    missed = make_assignment(
        vacancy=make_published_vacancy(now=now, starts_in_hours=300), worker=worker, now=now
    )
    assignments.mark_no_show(missed, now=now)
    worker.refresh_from_db()
    assert worker.level == L.BRONZE


# Perfil, candidatos e parâmetros ------------------------------------------------------------


def test_profile_shows_level_and_what_is_missing():
    worker = make_worker()
    paid(worker, 3, rating=5)
    client = APIClient()
    client.force_login(worker.user)
    data = client.get("/api/workers/me/").json()["level"]
    assert data["code"] == L.NEW
    assert data["label"] == "Novo"
    assert data["next"]["label"] == "Bronze"
    assert data["next"]["summary"] == "Faltam 2 turnos pagos para o nível Bronze"


def test_profile_explains_missing_rating():
    worker = make_worker()
    paid(worker, 5)
    client = APIClient()
    client.force_login(worker.user)
    summary = client.get("/api/workers/me/").json()["level"]["next"]["summary"]
    assert "você ainda não tem avaliações" in summary


def test_gold_has_no_next_level():
    worker = make_worker()
    paid(worker, 30, rating=5)
    levels.recalculate(worker, now=LATER)
    worker.refresh_from_db()
    assert levels.serialize(worker, now=LATER)["next"] is None


def test_candidates_list_shows_the_level_badge():
    worker = make_worker()
    Worker.objects.filter(pk=worker.pk).update(level=L.SILVER)
    now = timezone.now()
    vacancy = make_published_vacancy(now=now)
    applications.apply_to_vacancy(vacancy, worker, now=now)
    client = APIClient()
    client.force_login(vacancy.company.members.first().user)
    [candidate] = client.get(f"/api/vacancies/{vacancy.pk}/candidates/").json()["candidates"]
    assert (candidate["level"], candidate["level_label"]) == ("PRATA", "Prata")


def test_admin_edits_level_parameters_with_validation(client):
    client.force_login(make_admin())
    url = reverse("admin:core_platformparameters_change", args=[1])
    assert client.post(url, admin_payload(level_bronze_rating="5.5")).status_code == 200
    assert client.post(url, admin_payload(level_silver_shifts=40)).status_code == 200
    assert client.post(url, admin_payload(level_window_days=0)).status_code == 200
    response = client.post(url, admin_payload(level_gold_shifts=40, level_gold_rating="4.8"))
    assert response.status_code == 302
    params = PlatformParameters.get()
    assert params.level_gold_shifts == 40
    assert str(params.level_gold_rating) == "4.8"
