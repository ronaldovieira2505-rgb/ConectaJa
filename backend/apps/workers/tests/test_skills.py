"""US08 — habilidades e experiência do prestador."""

import pytest
from rest_framework.test import APIClient

from apps.core.tests.factories import NOW, make_company, make_published_vacancy, make_worker
from apps.vacancies import application_services as applications

pytestmark = pytest.mark.django_db

URL = "/api/workers/me/"


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def test_worker_saves_categories_and_summary_and_sees_them_in_the_profile():
    worker = make_worker()
    client = client_for(worker.user)

    response = client.patch(
        URL,
        {"skills": ["LIMPEZA", "EVENTOS"], "bio": "  Três anos em limpeza pós-obra.  "},
        format="json",
    )

    assert response.status_code == 200
    body = client.get(URL).json()
    assert body["skills"] == [
        {"value": "LIMPEZA", "label": "Limpeza"},
        {"value": "EVENTOS", "label": "Eventos"},
    ]
    assert body["bio"] == "Três anos em limpeza pós-obra."
    worker.refresh_from_db()
    assert worker.skills == ["LIMPEZA", "EVENTOS"]


def test_only_sent_fields_change():
    worker = make_worker()
    client = client_for(worker.user)
    client.patch(URL, {"skills": ["VAREJO"], "bio": "Caixa de mercado."}, format="json")

    client.patch(URL, {"bio": "Repositor e caixa."}, format="json")

    worker.refresh_from_db()
    assert (worker.skills, worker.bio) == (["VAREJO"], "Repositor e caixa.")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"skills": ["LIMPEZA"] * 4 + ["EVENTOS", "VAREJO", "FOTOGRAFIA", "OUTROS"]},
            "no máximo 7 categorias",
        ),
        ({"skills": ["LIMPEZA", "LIMPEZA"]}, "só pode aparecer uma vez"),
        ({"skills": ["PILOTO_DE_AVIAO"]}, "Categoria inexistente"),
        ({"skills": "LIMPEZA"}, "lista de categorias"),
        ({"bio": "x" * 501}, "no máximo 500 caracteres"),
        ({"bio": "Fale comigo: ana.silva@gmail.com"}, "e-mail nem telefone"),
        ({"bio": "Me chama no zap (11) 98888-7777"}, "e-mail nem telefone"),
        ({"bio": "Telefone 11988887777"}, "e-mail nem telefone"),
        ({"skills": ["LIMPEZA"], "bio": "meu email: a@b.com"}, "e-mail nem telefone"),
        ({}, "Informe as habilidades ou o resumo"),
        ({"cpf": "12345678909"}, "só é possível alterar as habilidades"),
    ],
)
def test_invalid_data_shows_error_and_saves_nothing(payload, message):
    worker = make_worker()

    response = client_for(worker.user).patch(URL, payload, format="json")

    assert response.status_code == 400
    assert message in response.json()["detail"]
    worker.refresh_from_db()
    assert (worker.skills, worker.bio) == ([], "")


def test_summary_with_numbers_that_are_not_a_phone_is_accepted():
    worker = make_worker()

    response = client_for(worker.user).patch(
        URL, {"bio": "Trabalhei de 2019 a 2023 em 2 mercados, turnos de 6 h."}, format="json"
    )

    assert response.status_code == 200


def test_summary_of_exactly_500_characters_is_accepted():
    worker = make_worker()

    response = client_for(worker.user).patch(URL, {"bio": "a" * 500}, format="json")

    assert response.status_code == 200


def test_company_cannot_change_worker_skills():
    company_user = make_company().members.first().user

    response = client_for(company_user).patch(URL, {"skills": ["LIMPEZA"]}, format="json")

    assert response.status_code == 403


def test_complete_your_profile_shows_skills_as_an_optional_step():
    worker = make_worker()
    client = client_for(worker.user)

    before = client.get(URL).json()["profile_steps"][-1]
    client.patch(URL, {"skills": ["LIMPEZA"]}, format="json")
    after = client.get(URL).json()["profile_steps"][-1]

    assert before == {
        "key": "habilidades",
        "label": "Habilidades e experiência",
        "done": False,
        "optional": True,
    }
    assert after["done"] is True


def candidates_of(vacancy):
    company_user = vacancy.company.members.first().user
    return client_for(company_user).get(f"/api/vacancies/{vacancy.pk}/candidates/").json()


def test_company_sees_summary_and_categories_with_the_vacancy_category_highlighted():
    vacancy = make_published_vacancy(category="LIMPEZA")
    worker = make_worker(skills=["EVENTOS", "LIMPEZA"], bio="Limpeza de escritórios.")
    applications.apply_to_vacancy(vacancy, worker, now=NOW)

    candidate = candidates_of(vacancy)["candidates"][0]

    assert candidate["bio"] == "Limpeza de escritórios."
    assert candidate["skills"] == [
        {"value": "EVENTOS", "label": "Eventos", "matches_vacancy": False},
        {"value": "LIMPEZA", "label": "Limpeza", "matches_vacancy": True},
    ]


def test_candidate_without_skills_has_empty_list_and_summary():
    vacancy = make_published_vacancy()
    applications.apply_to_vacancy(vacancy, make_worker(), now=NOW)

    candidate = candidates_of(vacancy)["candidates"][0]

    assert (candidate["skills"], candidate["bio"]) == ([], "")
