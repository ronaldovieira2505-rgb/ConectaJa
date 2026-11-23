"""US09 — fotos de trabalhos anteriores do prestador."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.core.tests.factories import NOW, make_company, make_published_vacancy, make_worker
from apps.vacancies import application_services as applications
from apps.workers.models import PortfolioPhoto

pytestmark = pytest.mark.django_db

URL = "/api/workers/me/portfolio/"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    return tmp_path / "private"


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def image(content=PNG, name="obra.png"):
    return SimpleUploadedFile(name, content, content_type="image/png")


def upload(client, caption="", content=PNG, name="obra.png"):
    return client.post(URL, {"photo": image(content, name), "caption": caption}, format="multipart")


def test_worker_adds_a_photo_with_caption_and_sees_it_in_the_profile():
    worker = make_worker()
    client = client_for(worker.user)

    response = upload(client, caption="Pintura de fachada em 2025")

    assert response.status_code == 201
    profile = client.get("/api/workers/me/").json()
    assert len(profile["portfolio"]) == 1
    item = profile["portfolio"][0]
    assert item["caption"] == "Pintura de fachada em 2025"
    assert item["url"] == f"/api/workers/portfolio/{item['id']}/file/"
    assert b"".join(client.get(item["url"]).streaming_content) == PNG


def test_limit_of_eight_photos():
    worker = make_worker()
    client = client_for(worker.user)
    for _ in range(8):
        assert upload(client).status_code == 201

    response = upload(client)

    assert response.status_code == 400
    assert "Remova uma" in response.json()["detail"]
    assert PortfolioPhoto.objects.filter(worker=worker).count() == 8


def test_removing_deletes_the_photo_and_the_file(private_media, django_capture_on_commit_callbacks):
    worker = make_worker()
    client = client_for(worker.user)
    photo_id = upload(client).json()["results"][0]["id"]

    with django_capture_on_commit_callbacks(execute=True):
        response = client.delete(f"{URL}{photo_id}/")

    assert response.status_code == 204
    assert not PortfolioPhoto.objects.exists()
    assert not list((private_media / "worker_portfolio").glob("*"))


@pytest.mark.parametrize(
    ("content", "name", "message"),
    [
        (b"%PDF-1.4" + b"\x00" * 64, "obra.pdf", "JPG, PNG ou WebP"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024), "grande.png", "5 MB"),
    ],
    # Nomes curtos: sem isso o pytest usa os 5 MB de bytes como nome do caso, e o Windows
    # recusa uma variável de ambiente desse tamanho (PYTEST_CURRENT_TEST).
    ids=["nao-e-imagem", "grande-demais"],
)
def test_invalid_file_shows_error_and_saves_nothing(content, name, message):
    worker = make_worker()

    response = upload(client_for(worker.user), content=content, name=name)

    assert response.status_code == 400
    assert message in response.json()["detail"]
    assert not PortfolioPhoto.objects.exists()


def test_caption_over_120_characters_is_refused():
    worker = make_worker()

    response = upload(client_for(worker.user), caption="x" * 121)

    assert response.status_code == 400
    assert not PortfolioPhoto.objects.exists()


def test_only_the_owner_removes_a_photo():
    owner, other = make_worker(), make_worker()
    photo_id = upload(client_for(owner.user)).json()["results"][0]["id"]

    response = client_for(other.user).delete(f"{URL}{photo_id}/")

    assert response.status_code == 404
    assert PortfolioPhoto.objects.filter(pk=photo_id).exists()


def test_photos_are_private():
    worker = make_worker()
    photo_url = upload(client_for(worker.user)).json()["results"][0]["url"]
    stranger_company = make_company().members.first().user

    assert APIClient().get(photo_url).status_code in (403, 404)
    assert client_for(make_worker().user).get(photo_url).status_code == 404
    assert client_for(stranger_company).get(photo_url).status_code == 404


def test_company_with_an_application_from_the_worker_can_see_the_photos():
    worker = make_worker()
    photo_url = upload(client_for(worker.user)).json()["results"][0]["url"]
    vacancy = make_published_vacancy()
    applications.apply_to_vacancy(vacancy, worker, now=NOW)
    company_user = vacancy.company.members.first().user

    assert client_for(company_user).get(photo_url).status_code == 200


def test_company_cannot_upload_photos():
    company_user = make_company().members.first().user

    response = upload(client_for(company_user))

    assert response.status_code == 403


def test_account_deletion_removes_portfolio_photos(django_capture_on_commit_callbacks):
    worker = make_worker()
    client = client_for(worker.user)
    upload(client)

    with django_capture_on_commit_callbacks(execute=True):
        client.post("/api/workers/me/delete/", {"password": "senha-forte-123"}, format="json")

    assert not PortfolioPhoto.objects.exists()
