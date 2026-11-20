"""US41 — a empresa vê as fotos de trabalhos anteriores do candidato."""

import pytest
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from apps.core.tests.factories import NOW, make_company, make_published_vacancy, make_worker
from apps.vacancies import application_services as applications
from apps.workers.models import PortfolioPhoto

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def with_photos(worker, count):
    for i in range(count):
        photo = PortfolioPhoto(worker=worker, caption=f"Trabalho {i + 1}")
        photo.file.save(f"{worker.pk}-{i}.png", ContentFile(PNG), save=True)
    return worker


def candidates(vacancy, user=None):
    user = user or vacancy.company.members.first().user
    return client_for(user).get(f"/api/vacancies/{vacancy.pk}/candidates/").json()["candidates"]


def test_candidate_brings_all_photos_with_captions_in_order():
    vacancy = make_published_vacancy()
    worker = with_photos(make_worker(), 6)
    applications.apply_to_vacancy(vacancy, worker, now=NOW)

    photos = candidates(vacancy)[0]["portfolio"]

    assert [p["caption"] for p in photos] == [f"Trabalho {i}" for i in range(1, 7)]
    assert photos[0]["url"] == f"/api/workers/portfolio/{photos[0]['id']}/file/"


def test_company_of_the_vacancy_opens_the_photo_and_another_company_cannot():
    vacancy = make_published_vacancy()
    worker = with_photos(make_worker(), 1)
    applications.apply_to_vacancy(vacancy, worker, now=NOW)
    url = candidates(vacancy)[0]["portfolio"][0]["url"]
    other_company = make_company().members.first().user

    assert client_for(vacancy.company.members.first().user).get(url).status_code == 200
    assert client_for(other_company).get(url).status_code == 404


def test_candidate_without_photos_has_an_empty_list():
    vacancy = make_published_vacancy()
    applications.apply_to_vacancy(vacancy, make_worker(), now=NOW)

    assert candidates(vacancy)[0]["portfolio"] == []
