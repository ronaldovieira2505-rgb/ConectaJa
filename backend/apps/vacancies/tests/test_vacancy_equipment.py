"""US22 — EPIs, uniforme e ferramentas que o prestador leva ou a empresa fornece."""

import pytest
from rest_framework.test import APIClient

from apps.core.tests.factories import make_company
from apps.vacancies.models import Vacancy, VacancyChange
from apps.vacancies.tests.test_vacancy_api import create, login_as

pytestmark = pytest.mark.django_db

EQUIPMENT = [
    {"item": "LUVAS", "provider": "EMPRESA"},
    {"item": "BOTINA", "provider": "PRESTADOR"},
    {"item": "CAPACETE", "provider": "EMPRESA"},
]


def published(client, **overrides):
    vacancy_id = create(client, **overrides).data["id"]
    client.post(f"/api/vacancies/{vacancy_id}/pay/")
    return vacancy_id


def test_company_marks_items_and_notes_when_creating():
    client = login_as(make_company())

    response = create(client, equipment=EQUIPMENT, equipment_notes="Trazer documento com foto.")

    assert response.status_code == 201
    vacancy = Vacancy.objects.get(pk=response.data["id"])
    # Guardado na ordem da lista fixa, não na ordem do envio.
    assert [e["item"] for e in vacancy.equipment] == ["CAPACETE", "LUVAS", "BOTINA"]
    assert vacancy.equipment_notes == "Trazer documento com foto."
    assert response.data["equipment"] == vacancy.equipment


def test_worker_sees_what_to_bring_and_what_is_provided_separately():
    client = login_as(make_company())
    vacancy_id = published(client, equipment=EQUIPMENT, equipment_notes="Portaria pela Rua B.")

    data = APIClient().get(f"/api/vacancies/{vacancy_id}/").json()

    assert data["equipment"] == {
        "bring": ["Botina"],
        "provided": ["Capacete", "Luvas"],
        "notes": "Portaria pela Rua B.",
    }


def test_vacancy_without_items_has_empty_lists():
    client = login_as(make_company())
    vacancy_id = published(client)

    data = APIClient().get(f"/api/vacancies/{vacancy_id}/").json()

    assert data["equipment"] == {"bring": [], "provided": [], "notes": ""}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"equipment": [{"item": "LANTERNA", "provider": "EMPRESA"}]}, "fora da lista"),
        ({"equipment": [{"item": "LUVAS", "provider": "NINGUEM"}]}, "prestador leva"),
        (
            {"equipment": [{"item": "LUVAS", "provider": "EMPRESA"}] * 2},
            "só pode aparecer uma vez",
        ),
        ({"equipment": "LUVAS"}, "lista"),
        ({"equipment_notes": "x" * 301}, "no máximo 300 caracteres"),
    ],
)
def test_invalid_items_or_notes_are_refused(overrides, message):
    client = login_as(make_company())

    response = create(client, **overrides)

    assert response.status_code == 400
    assert message in response.json()["detail"]
    assert not Vacancy.objects.exists()


def test_editing_items_follows_edit_rules_and_is_audited():
    company = make_company()
    client = login_as(company)
    vacancy_id = published(client, equipment=[{"item": "LUVAS", "provider": "EMPRESA"}])

    response = client.patch(
        f"/api/vacancies/{vacancy_id}/",
        {
            "equipment": [{"item": "LUVAS", "provider": "PRESTADOR"}],
            "equipment_notes": "Sem anéis.",
        },
        format="json",
    )

    assert response.status_code == 200
    changes = {c.field: c for c in VacancyChange.objects.filter(vacancy_id=vacancy_id)}
    assert set(changes) == {"equipment", "equipment_notes"}
    assert changes["equipment"].old_value == "Luvas (a empresa fornece)"
    assert changes["equipment"].new_value == "Luvas (o prestador leva)"
    assert changes["equipment_notes"].new_value == "Sem anéis."


def test_invalid_item_on_edit_is_refused():
    client = login_as(make_company())
    vacancy_id = published(client)

    response = client.patch(
        f"/api/vacancies/{vacancy_id}/",
        {"equipment": [{"item": "LANTERNA", "provider": "EMPRESA"}]},
        format="json",
    )

    assert response.status_code == 400
    assert Vacancy.objects.get(pk=vacancy_id).equipment == []
