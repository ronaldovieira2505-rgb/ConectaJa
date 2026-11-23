"""Latitude e longitude opcionais na criação da vaga: sem elas, o ponto vem do endereço."""

from decimal import Decimal

import pytest

from apps.core.tests.factories import make_company
from apps.vacancies.models import Vacancy
from apps.vacancies.tests.test_vacancy_api import create, login_as, payload

pytestmark = pytest.mark.django_db


def test_sem_coordenadas_busca_o_ponto_pelo_endereco(fake_geocoder):
    response = create(login_as(make_company()), latitude="", longitude="", number="1000")
    assert response.status_code == 201
    vacancy = Vacancy.objects.get()
    assert (vacancy.latitude, vacancy.longitude) == (Decimal("-23.561414"), Decimal("-46.655881"))
    assert fake_geocoder.calls == [
        {"street": "Praça da Sé", "number": "1000", "city": "São Paulo", "state": "SP"}
    ]


def test_campos_ausentes_tambem_usam_o_endereco(fake_geocoder):
    client = login_as(make_company())
    data = payload()
    data.pop("latitude")
    data.pop("longitude")
    response = client.post("/api/vacancies/", data, format="json")
    assert response.status_code == 201
    assert len(fake_geocoder.calls) == 1


def test_com_coordenadas_nao_consulta_o_mapa(fake_geocoder):
    response = create(login_as(make_company()))
    assert response.status_code == 201
    assert fake_geocoder.calls == []
    assert Vacancy.objects.get().latitude == Decimal("-23.550520")


def test_endereco_nao_encontrado_explica_o_que_fazer(fake_geocoder):
    fake_geocoder.fail = True
    response = create(login_as(make_company()), latitude="", longitude="")
    assert response.status_code == 400
    assert "Não encontramos esse endereço" in response.data["detail"]
    assert Vacancy.objects.count() == 0


def test_sem_coordenadas_e_sem_endereco_pede_endereco_ou_localizacao(fake_geocoder):
    response = create(login_as(make_company()), latitude="", longitude="", street="", city="")
    assert response.status_code == 400
    assert "Usar minha localização" in response.data["detail"]
    assert fake_geocoder.calls == []


def test_so_uma_coordenada_e_recusada(fake_geocoder):
    response = create(login_as(make_company()), longitude="")
    assert response.status_code == 400
    assert "latitude e longitude juntas" in response.data["detail"]


def test_edicao_com_coordenadas_em_branco_mantem_o_ponto(fake_geocoder):
    client = login_as(make_company())
    vacancy_id = create(client).data["id"]
    assert client.post(f"/api/vacancies/{vacancy_id}/pay/").status_code == 200
    response = client.patch(
        f"/api/vacancies/{vacancy_id}/", {"title": "Novo título", "latitude": "", "longitude": ""},
        format="json",
    )
    assert response.status_code == 200, response.data
    vacancy = Vacancy.objects.get()
    assert vacancy.title == "Novo título"
    assert vacancy.latitude == Decimal("-23.550520")
