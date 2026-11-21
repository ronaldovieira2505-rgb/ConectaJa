"""Detalhe de vaga encerrada para quem participou dela.

"Meus trabalhos" (concluídas/encerradas) e a Carteira têm link para `/vagas/<id>`. Antes, uma
vaga finalizada ou cancelada respondia 404 e a página mostrava "Vaga não encontrada".
"""

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.tests.factories import make_assignment, make_company, make_worker
from apps.vacancies import application_services as applications
from apps.vacancies.models import Vacancy

pytestmark = pytest.mark.django_db

V = Vacancy.Status


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_login(user)
    return client


def closed_assignment(status=V.FINISHED):
    assignment = make_assignment(now=timezone.now(), starts_in_hours=48)
    Vacancy.objects.filter(pk=assignment.vacancy_id).update(status=status)
    return assignment


@pytest.mark.parametrize(
    ("status", "notice"),
    [(V.FINISHED, "Esta vaga foi finalizada."), (V.CANCELLED, "Esta vaga foi cancelada.")],
)
def test_worker_who_worked_there_sees_the_closed_vacancy(status, notice):
    assignment = closed_assignment(status)
    response = client_for(assignment.worker.user).get(f"/api/vacancies/{assignment.vacancy_id}/")
    assert response.status_code == 200
    data = response.json()
    assert data["closed"] is True
    assert data["can_apply"] is False
    assert data["apply_blocker"] == notice
    assert data["my_application"]["status"] == "APROVADA"


def test_worker_whose_application_was_not_approved_also_sees_it():
    now = timezone.now()
    assignment = make_assignment(now=now, starts_in_hours=48)
    other = make_worker()
    Vacancy.objects.filter(pk=assignment.vacancy_id).update(positions=2)
    applications.apply_to_vacancy(assignment.vacancy, other, now=now)
    Vacancy.objects.filter(pk=assignment.vacancy_id).update(status=V.FINISHED)
    response = client_for(other.user).get(f"/api/vacancies/{assignment.vacancy_id}/")
    assert response.status_code == 200
    assert response.json()["my_application"]["status"] == "PENDENTE"


def test_closed_vacancy_stays_hidden_from_everyone_else():
    assignment = closed_assignment()
    url = f"/api/vacancies/{assignment.vacancy_id}/"
    assert client_for().get(url).status_code == 404
    assert client_for(make_worker().user).get(url).status_code == 404
    assert client_for(make_company().members.first().user).get(url).status_code == 404


def test_open_vacancy_is_not_marked_closed():
    assignment = make_assignment(now=timezone.now(), starts_in_hours=48)
    data = client_for(make_worker().user).get(f"/api/vacancies/{assignment.vacancy_id}/").json()
    assert data["closed"] is False


def test_closed_vacancy_does_not_appear_in_search():
    assignment = closed_assignment()
    results = client_for(assignment.worker.user).get("/api/vacancies/").json()["results"]
    assert assignment.vacancy_id not in [v["id"] for v in results]
