"""US25 — duplicar uma vaga já publicada."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.core.tests.factories import make_assignment, make_company
from apps.payments.models import Custody
from apps.vacancies import photos
from apps.vacancies.models import Vacancy
from apps.vacancies.tests.test_vacancy_api import create, login_as

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 64


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"


def with_photo(vacancy):
    photos.set_photo(vacancy, SimpleUploadedFile("local.png", PNG, content_type="image/png"))
    vacancy.refresh_from_db()
    return vacancy


def test_duplicate_is_a_new_vacancy_awaiting_payment_with_its_own_custody():
    company = make_company()
    client = login_as(company)
    original = Vacancy.objects.get(pk=create(client).data["id"])
    client.post(f"/api/vacancies/{original.pk}/pay/")
    make_assignment(vacancy=Vacancy.objects.get(pk=original.pk), now=timezone.now())

    response = create(client, duplicate_of=original.pk, title="Carga e descarga (cópia)")

    assert response.status_code == 201
    copy = Vacancy.objects.get(pk=response.data["id"])
    assert copy.pk != original.pk
    assert copy.status == Vacancy.Status.AWAITING_PAYMENT
    assert copy.title == "Carga e descarga (cópia)"
    assert copy.custody.status == Custody.Status.PENDING
    assert copy.custody.pk != original.custody.pk
    assert not copy.applications.exists()
    assert not copy.assignments.exists()


def test_duplicate_gets_its_own_copy_of_the_photo():
    company = make_company()
    client = login_as(company)
    original = with_photo(Vacancy.objects.get(pk=create(client).data["id"]))

    response = create(client, duplicate_of=original.pk)

    copy = Vacancy.objects.get(pk=response.data["id"])
    assert copy.photo.name and copy.photo.name != original.photo.name
    with copy.photo.open("rb") as handle:
        assert handle.read() == PNG
    assert response.data["photo_url"].startswith(f"/api/vacancies/{copy.pk}/photo/?v=")
    photos.remove_photo(copy)
    original.refresh_from_db()
    with original.photo.open("rb") as handle:
        assert handle.read() == PNG  # apagar a cópia não apaga a original


def test_duplicate_of_vacancy_without_photo_has_no_photo():
    client = login_as(make_company())
    original_id = create(client).data["id"]

    response = create(client, duplicate_of=original_id)

    assert response.data["photo_url"] is None


def test_any_state_can_be_duplicated():
    client = login_as(make_company())
    original_id = create(client).data["id"]
    client.post(f"/api/vacancies/{original_id}/pay/")
    client.post(f"/api/vacancies/{original_id}/remove/")
    assert Vacancy.objects.get(pk=original_id).status == Vacancy.Status.CANCELLED

    response = create(client, duplicate_of=original_id)

    assert response.status_code == 201


def test_minimum_lead_time_still_applies_to_the_duplicate():
    client = login_as(make_company())
    original_id = create(client).data["id"]
    soon = timezone.now() + timedelta(hours=1)

    response = create(
        client,
        duplicate_of=original_id,
        starts_at=soon.isoformat(),
        ends_at=(soon + timedelta(hours=4)).isoformat(),
    )

    assert response.status_code == 400
    assert Vacancy.objects.count() == 1


def test_company_cannot_duplicate_another_companys_vacancy():
    original_id = create(login_as(make_company())).data["id"]
    other = login_as(make_company())

    response = create(other, duplicate_of=original_id)

    assert response.status_code == 404
    assert Vacancy.objects.count() == 1


def test_unknown_vacancy_cannot_be_duplicated():
    response = create(login_as(make_company()), duplicate_of=999999)

    assert response.status_code == 404
    assert not Vacancy.objects.exists()


def test_company_detail_has_every_field_needed_to_fill_the_form():
    client = login_as(make_company())
    original_id = create(client, number="111", district="Sé", zip_code="01001000").data["id"]

    data = client.get(f"/api/vacancies/{original_id}/").json()

    for field in (
        "title",
        "category",
        "description",
        "street",
        "number",
        "complement",
        "district",
        "city",
        "state",
        "zip_code",
        "latitude",
        "longitude",
        "pay_per_person_cents",
        "positions",
        "photo_url",
    ):
        assert field in data
    assert (data["number"], data["district"], data["zip_code"]) == ("111", "Sé", "01001000")
