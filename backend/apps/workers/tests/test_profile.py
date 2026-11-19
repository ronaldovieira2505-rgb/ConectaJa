import pytest
from rest_framework.test import APIClient

from apps.core.models import PlatformParameters
from apps.core.tests.factories import make_paid_ready_assignment, make_worker
from apps.vacancies import assignment_services as assignments
from apps.vacancies.models import Review

pytestmark = pytest.mark.django_db


def profile_of(worker):
    client = APIClient()
    client.force_login(worker.user)
    return client.get("/api/workers/me/").data


def test_perfil_novo_comeca_sem_foto_e_com_numeros_zerados():
    data = profile_of(make_worker())

    assert data["photo_url"] is None
    assert data["stats"] == {
        "completed_shifts": 0,
        "total_received_cents": 0,
        "rating_average": None,
        "rating_count": 0,
    }
    assert data["reviews"] == []
    assert [document["uploaded"] for document in data["documents"]] == [False, False, False]


def test_perfil_soma_turnos_pagos_valor_recebido_e_avaliacoes():
    assignment = make_paid_ready_assignment()
    assignment = assignments.settle(assignment)
    company_user = assignment.vacancy.company.members.first().user
    Review.objects.create(
        assignment=assignment,
        direction=Review.Direction.COMPANY_TO_WORKER,
        author=company_user,
        rating=4,
        comment="Pontual e cuidadoso.",
    )

    data = profile_of(assignment.worker)

    net = PlatformParameters.get().worker_net_cents(assignment.vacancy.pay_per_person_cents)
    assert data["stats"] == {
        "completed_shifts": 1,
        "total_received_cents": net,
        "rating_average": 4.0,
        "rating_count": 1,
    }
    assert data["reviews"][0]["comment"] == "Pontual e cuidadoso."
    assert data["reviews"][0]["vacancy_title"] == assignment.vacancy.title
