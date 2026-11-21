"""Admin com arquivos privados: a página abre e o arquivo aparece só como link protegido.

Antes, o widget de arquivo do admin pedia a URL ao `PrivateMediaStorage`, que não tem URL
pública de propósito, e a página dava erro 500.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.core.tests.factories import make_admin, make_company, make_published_vacancy, make_worker
from apps.workers.models import PrivateMediaStorage, WorkerDocument

pytestmark = pytest.mark.django_db

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(autouse=True)
def private_root(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"


@pytest.fixture
def admin_client(client):
    client.force_login(make_admin())
    return client


def image(name):
    return SimpleUploadedFile(name, PNG, content_type="image/png")


def test_worker_with_documents_opens_and_links_to_the_protected_endpoint(admin_client):
    worker = make_worker()
    WorkerDocument.objects.create(worker=worker, kind="SELFIE", file=image("selfie.png"))
    response = admin_client.get(reverse("admin:workers_worker_change", args=[worker.pk]))
    assert response.status_code == 200
    assert f"/api/workers/{worker.pk}/documents/SELFIE/" in response.content.decode()


def test_company_with_logo_opens_and_links_to_the_logo(admin_client):
    company = make_company()
    company.logo = image("logo.png")
    company.save()
    response = admin_client.get(reverse("admin:companies_company_change", args=[company.pk]))
    assert response.status_code == 200
    assert f"/api/companies/{company.pk}/logo/" in response.content.decode()


def test_vacancy_with_photo_opens_and_links_to_the_photo(admin_client):
    vacancy = make_published_vacancy()
    vacancy.photo = image("local.png")
    vacancy.save()
    response = admin_client.get(reverse("admin:vacancies_vacancy_change", args=[vacancy.pk]))
    assert response.status_code == 200
    assert f"/api/vacancies/{vacancy.pk}/photo/" in response.content.decode()


def test_saving_the_company_in_the_admin_keeps_the_logo(admin_client):
    company = make_company()
    company.logo = image("logo.png")
    company.save()
    name = company.logo.name
    url = reverse("admin:companies_company_change", args=[company.pk])
    page = admin_client.get(url)
    form = page.context["adminform"].form
    data = {k: ("" if v is None else v) for k, v in form.initial.items() if k in form.fields}
    data.update(
        {
            "companymember_set-TOTAL_FORMS": "0",
            "companymember_set-INITIAL_FORMS": "0",
            "companymember_set-MIN_NUM_FORMS": "0",
            "companymember_set-MAX_NUM_FORMS": "1000",
        }
    )
    admin_client.post(url, data)
    company.refresh_from_db()
    assert company.logo.name == name


def test_private_files_still_have_no_public_url():
    with pytest.raises(ValueError):
        PrivateMediaStorage().url("worker_documents/selfie.png")
