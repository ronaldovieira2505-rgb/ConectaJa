"""US69: o prestador denuncia uma vaga ou empresa suspeita."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Notification, StateTransition
from apps.core.tests.factories import (
    make_admin,
    make_company,
    make_published_vacancy,
    make_worker,
    vacancy_fields,
)
from apps.reports.models import Report
from apps.vacancies import services as vacancies

pytestmark = pytest.mark.django_db

URL = "/api/reports/"
DESCRIPTION = "Pediram um PIX adiantado para garantir a vaga."


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def report(user, **data):
    payload = {"reason": "PAGAMENTO_POR_FORA", "description": DESCRIPTION, **data}
    return client_for(user).post(URL, payload, format="json")


def published():
    return make_published_vacancy(now=timezone.now())


def test_worker_reports_a_vacancy_and_admin_is_notified():
    admin = make_admin()
    worker = make_worker()
    vacancy = published()
    response = report(worker.user, target_type="VAGA", target_id=vacancy.pk)
    assert response.status_code == 201
    assert response.json()["detail"] == "Denúncia enviada. A equipe vai analisar."
    assert response.json()["status"] == "ABERTA"

    saved = Report.objects.get()
    assert saved.reporter == worker.user
    assert saved.target_type == "VAGA"
    assert saved.vacancy == vacancy
    assert saved.company == vacancy.company  # o alvo inclui a empresa dona da vaga
    assert saved.description == DESCRIPTION
    note = Notification.objects.get(user=admin, kind="DENUNCIA")
    assert "Pedido de pagamento por fora" in note.message
    assert StateTransition.objects.filter(
        entity_type="Report", entity_id=saved.pk, from_state="", to_state="ABERTA"
    ).exists()


def test_worker_reports_a_company():
    worker = make_worker()
    company = make_company()
    response = report(worker.user, target_type="EMPRESA", target_id=company.pk, reason="OUTRO")
    assert response.status_code == 201
    saved = Report.objects.get()
    assert (saved.target_type, saved.company, saved.vacancy) == ("EMPRESA", company, None)


def test_reported_company_is_not_notified_and_response_hides_nothing_about_it():
    worker = make_worker()
    vacancy = published()
    response = report(worker.user, target_type="VAGA", target_id=vacancy.pk)
    assert set(response.json()) == {"id", "status", "detail"}
    company_users = [m.user for m in vacancy.company.members.all()]
    assert not Notification.objects.filter(user__in=company_users, kind="DENUNCIA").exists()


def test_no_second_report_on_the_same_target_while_open():
    worker = make_worker()
    vacancy = published()
    assert report(worker.user, target_type="VAGA", target_id=vacancy.pk).status_code == 201
    response = report(worker.user, target_type="VAGA", target_id=vacancy.pk)
    assert response.status_code == 409
    assert "denúncia aberta" in response.json()["detail"]

    # "Em análise" ainda conta como aberta; concluída libera uma nova.
    Report.objects.update(status="EM_ANALISE")
    assert report(worker.user, target_type="VAGA", target_id=vacancy.pk).status_code == 409
    Report.objects.update(status="IMPROCEDENTE")
    assert report(worker.user, target_type="VAGA", target_id=vacancy.pk).status_code == 201


def test_duplicate_rule_is_per_target_and_per_person():
    worker, other = make_worker(), make_worker()
    vacancy = published()
    assert report(worker.user, target_type="VAGA", target_id=vacancy.pk).status_code == 201
    # A mesma pessoa pode denunciar a empresa (alvo diferente) e outra pessoa, a mesma vaga.
    company_id = vacancy.company_id
    assert report(worker.user, target_type="EMPRESA", target_id=company_id).status_code == 201
    assert report(other.user, target_type="VAGA", target_id=vacancy.pk).status_code == 201


@pytest.mark.parametrize(
    "description",
    ["", "curto", "   nove   ", "x" * 1001, None, 123],
)
def test_description_from_10_to_1000_characters(description):
    worker = make_worker()
    vacancy = published()
    response = report(
        worker.user, target_type="VAGA", target_id=vacancy.pk, description=description
    )
    assert response.status_code == 400
    assert not Report.objects.exists()


def test_description_with_exactly_10_and_1000_characters_is_accepted():
    worker = make_worker()
    first, second = published(), published()
    assert (
        report(
            worker.user, target_type="VAGA", target_id=first.pk, description="x" * 10
        ).status_code
        == 201
    )
    assert (
        report(
            worker.user, target_type="VAGA", target_id=second.pk, description="x" * 1000
        ).status_code
        == 201
    )


@pytest.mark.parametrize("reason", ["", "INVALIDO", None])
def test_reason_must_come_from_the_list(reason):
    worker = make_worker()
    vacancy = published()
    response = report(worker.user, target_type="VAGA", target_id=vacancy.pk, reason=reason)
    assert response.status_code == 400


@pytest.mark.parametrize("target", [{"target_type": "X", "target_id": 1}, {"target_id": 1}])
def test_invalid_target_type(target):
    assert report(make_worker().user, **target).status_code == 400


@pytest.mark.parametrize("target_id", ["1", None, True, 1.5])
def test_invalid_target_id(target_id):
    assert report(make_worker().user, target_type="EMPRESA", target_id=target_id).status_code == 400


def test_unknown_or_unpaid_target_is_404():
    worker = make_worker()
    assert report(worker.user, target_type="VAGA", target_id=999999).status_code == 404
    assert report(worker.user, target_type="EMPRESA", target_id=999999).status_code == 404
    now = timezone.now()
    unpaid = vacancies.create_vacancy(
        company=make_company(), now=now, **vacancy_fields(now + timedelta(days=2))
    )
    assert report(worker.user, target_type="VAGA", target_id=unpaid.pk).status_code == 404


def test_only_logged_in_workers_can_report():
    vacancy = published()
    anonymous = APIClient().post(
        URL,
        {
            "target_type": "VAGA",
            "target_id": vacancy.pk,
            "reason": "OUTRO",
            "description": DESCRIPTION,
        },
        format="json",
    )
    assert anonymous.status_code == 403
    company_user = make_company().members.first().user
    assert report(company_user, target_type="VAGA", target_id=vacancy.pk).status_code == 403
    assert report(make_admin(), target_type="VAGA", target_id=vacancy.pk).status_code == 403
    assert not Report.objects.exists()
