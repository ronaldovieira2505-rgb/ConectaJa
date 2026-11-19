import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.core.tests.factories import make_company
from apps.vacancies.models import Vacancy
from apps.vacancies.tests.test_vacancy_api import create, login_as

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"


def upload(client, vacancy_id, content=PNG, name="local.png", content_type="image/png"):
    photo = SimpleUploadedFile(name, content, content_type=content_type)
    return client.post(f"/api/vacancies/{vacancy_id}/photo/", {"photo": photo}, format="multipart")


def test_vaga_sem_foto_informa_endereco_nulo():
    response = create(login_as(make_company()))
    assert response.data["photo_url"] is None


def test_empresa_envia_foto_e_qualquer_pessoa_consegue_ver():
    client = login_as(make_company())
    vacancy_id = create(client).data["id"]

    response = upload(client, vacancy_id)

    assert response.status_code == 200
    url = response.data["photo_url"]
    assert url.startswith(f"/api/vacancies/{vacancy_id}/photo/?v=")
    public = APIClient().get(url)
    assert public.status_code == 200
    assert public["Content-Type"] == "image/png"
    assert b"".join(public.streaming_content) == PNG


def test_foto_aparece_no_cartao_da_busca():
    client = login_as(make_company())
    vacancy_id = create(client).data["id"]
    client.post(f"/api/vacancies/{vacancy_id}/pay/")
    url = upload(client, vacancy_id).data["photo_url"]

    cards = APIClient().get("/api/vacancies/").data["results"]

    assert [card["photo_url"] for card in cards] == [url]


def test_nova_foto_substitui_a_anterior_e_muda_o_endereco():
    client = login_as(make_company())
    vacancy_id = create(client).data["id"]
    first = upload(client, vacancy_id).data["photo_url"]
    old_path = Vacancy.objects.get(pk=vacancy_id).photo.path

    second = upload(client, vacancy_id, JPG, "local.jpg", "image/jpeg").data["photo_url"]

    assert second != first
    vacancy = Vacancy.objects.get(pk=vacancy_id)
    assert vacancy.photo.name.endswith(".jpg")
    assert not vacancy.photo.storage.exists(old_path)


@pytest.mark.parametrize(
    "content, message",
    [
        (b"%PDF-1.7 arquivo que nao e imagem", "JPG, PNG ou WebP"),
        (PNG + b"\x00" * (5 * 1024 * 1024), "5 MB"),
    ],
    ids=["nao-e-imagem", "grande-demais"],
)
def test_arquivo_invalido_e_recusado(content, message):
    client = login_as(make_company())
    vacancy_id = create(client).data["id"]

    # A extensão diz PNG, mas o que vale é o conteúdo.
    response = upload(client, vacancy_id, content)

    assert response.status_code == 400
    assert message in response.data["detail"]
    assert not Vacancy.objects.get(pk=vacancy_id).photo


def test_envio_sem_arquivo_e_recusado():
    client = login_as(make_company())
    vacancy_id = create(client).data["id"]
    response = client.post(f"/api/vacancies/{vacancy_id}/photo/", {}, format="multipart")
    assert response.status_code == 400


def test_outra_empresa_nao_altera_a_foto():
    owner = login_as(make_company())
    vacancy_id = create(owner).data["id"]
    upload(owner, vacancy_id)
    other = login_as(make_company())

    assert upload(other, vacancy_id).status_code == 404
    assert other.delete(f"/api/vacancies/{vacancy_id}/photo/").status_code == 404
    assert Vacancy.objects.get(pk=vacancy_id).photo


def test_visitante_nao_envia_foto():
    vacancy_id = create(login_as(make_company())).data["id"]
    assert upload(APIClient(), vacancy_id).status_code == 403


def test_empresa_remove_a_foto():
    client = login_as(make_company())
    vacancy_id = create(client).data["id"]
    url = upload(client, vacancy_id).data["photo_url"]

    response = client.delete(f"/api/vacancies/{vacancy_id}/photo/")

    assert response.status_code == 200
    assert response.data["photo_url"] is None
    assert APIClient().get(url).status_code == 404


def test_vaga_cancelada_nao_aceita_foto():
    client = login_as(make_company())
    vacancy_id = create(client).data["id"]
    Vacancy.objects.filter(pk=vacancy_id).update(status=Vacancy.Status.CANCELLED)

    response = upload(client, vacancy_id)

    assert response.status_code == 409
