import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.core.tests.factories import (
    make_company,
    make_paid_ready_assignment,
    make_published_vacancy,
    make_worker,
)
from apps.vacancies import assignment_services as assignments

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"


def login_as(company):
    client = APIClient()
    client.force_login(company.members.first().user)
    return client


def upload(client, content=PNG):
    logo = SimpleUploadedFile("logo.png", content, content_type="image/png")
    return client.post("/api/companies/me/logo/", {"logo": logo}, format="multipart")


def test_empresa_ve_o_proprio_cadastro_e_os_numeros():
    company = make_company()
    make_published_vacancy(company=company)

    response = login_as(company).get("/api/companies/me/")

    assert response.status_code == 200
    assert response.data["legal_name"] == company.legal_name
    assert response.data["cnpj"] == company.cnpj
    assert response.data["verification_status"] == "APROVADA"
    assert response.data["logo_url"] is None
    assert response.data["stats"] == {
        "published_vacancies": 1,
        "finished_vacancies": 0,
        "completed_shifts": 0,
        "total_paid_cents": 0,
    }


def test_numeros_contam_turnos_pagos_e_valor_repassado():
    assignment = make_paid_ready_assignment()
    assignment = assignments.settle(assignment)
    company = assignment.vacancy.company

    stats = login_as(company).get("/api/companies/me/").data["stats"]

    assert stats["completed_shifts"] == 1
    assert stats["total_paid_cents"] == assignment.vacancy.pay_per_person_cents


def test_empresa_edita_apresentacao_mas_nao_os_dados_fiscais():
    company = make_company()
    client = login_as(company)

    response = client.patch(
        "/api/companies/me/",
        {"description": "  Rede de mercados de bairro.  ", "legal_name": "Outra LTDA"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["description"] == "Rede de mercados de bairro."
    company.refresh_from_db()
    assert company.legal_name != "Outra LTDA"


def test_empresa_envia_logo_que_fica_publica():
    company = make_company()
    client = login_as(company)

    response = upload(client)

    assert response.status_code == 200
    url = response.data["logo_url"]
    assert url.startswith(f"/api/companies/{company.pk}/logo/?v=")
    public = APIClient().get(url)
    assert public.status_code == 200
    assert public["Content-Type"] == "image/png"


def test_logo_que_nao_e_imagem_e_recusada():
    client = login_as(make_company())
    response = upload(client, b"%PDF-1.7 nao e imagem")
    assert response.status_code == 400
    assert "JPG, PNG ou WebP" in response.data["detail"]


def test_empresa_remove_a_logo():
    client = login_as(make_company())
    url = upload(client).data["logo_url"]

    response = client.delete("/api/companies/me/logo/")

    assert response.data["logo_url"] is None
    assert APIClient().get(url).status_code == 404


def test_prestador_e_visitante_nao_acessam_o_perfil_da_empresa():
    worker_client = APIClient()
    worker_client.force_login(make_worker().user)
    assert worker_client.get("/api/companies/me/").status_code == 403
    assert APIClient().get("/api/companies/me/").status_code == 403
