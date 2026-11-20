"""US18 — salvar vagas nos favoritos."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.tests.factories import (
    make_assignment,
    make_company,
    make_published_vacancy,
    make_worker,
)
from apps.vacancies import services as vacancies
from apps.vacancies.models import FavoriteVacancy, Vacancy

pytestmark = pytest.mark.django_db

LIST = "/api/workers/me/favorites/"


def favorite_url(vacancy_id):
    return f"/api/vacancies/{vacancy_id}/favorite/"


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def open_vacancy(hours=48, **kw):
    return make_published_vacancy(now=timezone.now(), starts_in_hours=hours, **kw)


def test_worker_saves_and_removes_a_favorite():
    worker = make_worker()
    client = client_for(worker.user)
    vacancy = open_vacancy()

    saved = client.post(favorite_url(vacancy.pk))
    listed = client.get(LIST).json()["results"]
    removed = client.delete(favorite_url(vacancy.pk))

    assert saved.status_code == 201
    assert saved.json() == {"vacancy_id": vacancy.pk, "favorite": True}
    assert [item["id"] for item in listed] == [vacancy.pk]
    assert listed[0]["favorite"] is True
    assert listed[0]["closed_label"] is None
    assert listed[0]["net_cents"] == 9700  # mesmo card da busca
    assert removed.status_code == 204
    assert client.get(LIST).json()["results"] == []


def test_favoriting_twice_does_not_duplicate_and_removing_twice_does_not_fail():
    worker = make_worker()
    client = client_for(worker.user)
    vacancy = open_vacancy()

    first, second = client.post(favorite_url(vacancy.pk)), client.post(favorite_url(vacancy.pk))
    client.delete(favorite_url(vacancy.pk))
    again = client.delete(favorite_url(vacancy.pk))

    assert (first.status_code, second.status_code) == (201, 200)
    assert again.status_code == 204
    assert not FavoriteVacancy.objects.exists()


def test_list_goes_from_the_soonest_start_to_the_latest():
    worker = make_worker()
    client = client_for(worker.user)
    later, sooner = open_vacancy(hours=96), open_vacancy(hours=24)
    client.post(favorite_url(later.pk))
    client.post(favorite_url(sooner.pk))

    ids = [item["id"] for item in client.get(LIST).json()["results"]]

    assert ids == [sooner.pk, later.pk]


def test_cancelled_vacancy_stays_in_the_list_as_closed():
    worker = make_worker()
    client = client_for(worker.user)
    vacancy = open_vacancy()
    client.post(favorite_url(vacancy.pk))

    vacancies.remove_vacancy(Vacancy.objects.get(pk=vacancy.pk))

    item = client.get(LIST).json()["results"][0]
    assert item["closed_label"] == "Encerrada"


def test_full_vacancy_stays_in_the_list_as_full():
    worker = make_worker()
    client = client_for(worker.user)
    vacancy = open_vacancy(positions=1)
    client.post(favorite_url(vacancy.pk))

    make_assignment(vacancy=vacancy, now=timezone.now())

    item = client.get(LIST).json()["results"][0]
    assert item["closed_label"] == "Lotada"
    assert item["remaining_positions"] == 0


def test_vacancy_whose_applications_closed_is_shown_as_closed():
    worker = make_worker()
    client = client_for(worker.user)
    vacancy = open_vacancy(hours=24)
    client.post(favorite_url(vacancy.pk))
    Vacancy.objects.filter(pk=vacancy.pk).update(
        starts_at=timezone.now() + timedelta(minutes=30),
        ends_at=timezone.now() + timedelta(hours=4),
    )

    item = client.get(LIST).json()["results"][0]

    assert item["closed_label"] == "Encerrada"


def test_each_worker_sees_only_their_own_favorites():
    mine, other = make_worker(), make_worker()
    vacancy = open_vacancy()
    client_for(other.user).post(favorite_url(vacancy.pk))

    assert client_for(mine.user).get(LIST).json()["results"] == []


def test_vacancy_not_yet_published_or_unknown_cannot_be_favorited():
    worker = make_worker()
    client = client_for(worker.user)
    unpaid = vacancies.create_vacancy(
        company=make_company(),
        title="Sem pagamento",
        category="OUTROS",
        description="x",
        latitude=-23.5,
        longitude=-46.6,
        starts_at=timezone.now() + timedelta(days=2),
        ends_at=timezone.now() + timedelta(days=2, hours=4),
        pay_per_person_cents=10000,
        positions=1,
    )

    assert client.post(favorite_url(unpaid.pk)).status_code == 404
    assert client.post(favorite_url(999999)).status_code == 404


def test_company_and_visitor_cannot_use_favorites():
    vacancy = open_vacancy()
    company_user = make_company().members.first().user

    assert client_for(company_user).post(favorite_url(vacancy.pk)).status_code == 403
    assert client_for(company_user).get(LIST).status_code == 403
    assert APIClient().post(favorite_url(vacancy.pk)).status_code == 403


def test_search_and_detail_tell_the_worker_which_vacancies_are_favorites():
    worker = make_worker()
    client = client_for(worker.user)
    saved, other = open_vacancy(), open_vacancy(hours=72)
    client.post(favorite_url(saved.pk))

    search = client.get("/api/vacancies/").json()["results"]
    results = {item["id"]: item["favorite"] for item in search}
    detail = client.get(f"/api/vacancies/{saved.pk}/").json()

    assert results == {saved.pk: True, other.pk: False}
    assert detail["favorite"] is True
    assert APIClient().get(f"/api/vacancies/{saved.pk}/").json()["favorite"] is False
