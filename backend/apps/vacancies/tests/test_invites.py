"""US44 — convidar de novo um prestador que já trabalhou bem com a empresa."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Notification
from apps.core.tests.factories import (
    LAT,
    LNG,
    make_assignment,
    make_company,
    make_published_vacancy,
    make_worker,
)
from apps.vacancies import application_services as applications
from apps.vacancies import assignment_services as assignments
from apps.vacancies.invites import MAX_INVITES
from apps.vacancies.models import Application, Review, VacancyInvite

pytestmark = pytest.mark.django_db


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def owner(company):
    return company.members.first().user


def paid_with(company, worker, rating=None, hours=48):
    """Turno pago do prestador na empresa (com a nota que a empresa deu, se houver)."""
    vacancy = make_published_vacancy(company=company, starts_in_hours=hours)
    assignment = make_assignment(vacancy=vacancy, worker=worker)
    start = vacancy.starts_at
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)
    assignments.check_out(assignment, now=start + timedelta(hours=4))
    assignments.approve_hours(assignment, now=start + timedelta(hours=5))
    assignment = assignments.settle(assignment, now=start + timedelta(hours=6))
    if rating:
        Review.objects.create(
            assignment=assignment,
            direction=Review.Direction.COMPANY_TO_WORKER,
            author=owner(company),
            rating=rating,
        )
    return assignment


def named(worker, full_name):
    worker.full_name = full_name
    worker.save(update_fields=["full_name"])
    return worker


def open_vacancy(company, **kw):
    return make_published_vacancy(company=company, now=timezone.now(), **kw)


def listing(company, vacancy):
    return client_for(owner(company)).get(f"/api/company/past-workers/?vacancy={vacancy.pk}").json()


def test_list_shows_past_workers_ordered_by_the_rating_given():
    company = make_company()
    ana = named(make_worker(), "Ana Paula Ribeiro")
    bruno = named(make_worker(), "Bruno Costa")
    paid_with(company, ana, rating=5)
    paid_with(company, ana, rating=4, hours=72)
    paid_with(company, bruno, rating=3)
    paid_with(make_company(), make_worker())  # trabalhou com outra empresa
    vacancy = open_vacancy(company)

    data = listing(company, vacancy)

    assert [r["name"] for r in data["results"]] == ["Ana R.", "Bruno C."]
    first = data["results"][0]
    assert (first["shifts_with_company"], first["rating_given"]) == (2, 4.5)
    assert first["invited"] is False and first["blocker"] is None
    assert (data["max_invites"], data["invites_left"]) == (20, 20)
    assert data["vacancy_blocker"] is None


def test_invite_notifies_the_worker_with_a_link_and_does_not_approve():
    company = make_company()
    worker = make_worker()
    paid_with(company, worker)
    vacancy = open_vacancy(company, title="Reposição de estoque")

    response = client_for(owner(company)).post(
        f"/api/vacancies/{vacancy.pk}/invite/", {"worker_id": worker.pk}, format="json"
    )

    assert response.status_code == 201
    note = Notification.objects.get(user=worker.user, kind="CONVITE_VAGA")
    assert note.title == f"A {company.legal_name} convidou você para Reposição de estoque"
    assert note.link == f"/vagas/{vacancy.pk}"
    assert not Application.objects.filter(vacancy=vacancy, worker=worker).exists()
    assert listing(company, vacancy)["results"][0]["invited"] is True


def test_the_same_worker_is_not_invited_twice():
    company = make_company()
    worker = make_worker()
    paid_with(company, worker)
    vacancy = open_vacancy(company)
    client = client_for(owner(company))
    url = f"/api/vacancies/{vacancy.pk}/invite/"

    client.post(url, {"worker_id": worker.pk}, format="json")
    again = client.post(url, {"worker_id": worker.pk}, format="json")

    assert again.status_code == 409
    assert VacancyInvite.objects.count() == 1


def test_suspended_applied_or_busy_workers_show_the_reason_and_cannot_be_invited():
    company = make_company()
    suspended, applied, busy = make_worker(), make_worker(), make_worker()
    for worker in (suspended, applied, busy):
        paid_with(company, worker)
    suspended.suspension_indefinite = True
    suspended.save(update_fields=["suspension_indefinite"])
    vacancy = open_vacancy(company, starts_in_hours=96)
    applications.apply_to_vacancy(vacancy, applied)
    other = open_vacancy(make_company(), starts_in_hours=96)
    make_assignment(vacancy=other, worker=busy, now=timezone.now())

    reasons = {r["worker_id"]: r["blocker"] for r in listing(company, vacancy)["results"]}
    response = client_for(owner(company)).post(
        f"/api/vacancies/{vacancy.pk}/invite/", {"worker_id": busy.pk}, format="json"
    )

    assert reasons == {
        suspended.pk: "Prestador suspenso.",
        applied.pk: "Já se candidatou a esta vaga.",
        busy.pk: "Tem outro turno nesse horário.",
    }
    assert response.status_code == 409


def test_full_vacancy_cannot_receive_invites():
    company = make_company()
    worker = make_worker()
    paid_with(company, worker)
    vacancy = open_vacancy(company, positions=1)
    make_assignment(vacancy=vacancy, now=timezone.now())

    data = listing(company, vacancy)
    response = client_for(owner(company)).post(
        f"/api/vacancies/{vacancy.pk}/invite/", {"worker_id": worker.pk}, format="json"
    )

    assert data["vacancy_blocker"] == "Esta vaga está lotada."
    assert response.status_code == 409


def test_limit_of_invites_per_vacancy():
    company = make_company()
    vacancy = open_vacancy(company)
    worker = make_worker()
    paid_with(company, worker)
    for _ in range(MAX_INVITES):
        VacancyInvite.objects.create(vacancy=vacancy, worker=make_worker())

    response = client_for(owner(company)).post(
        f"/api/vacancies/{vacancy.pk}/invite/", {"worker_id": worker.pk}, format="json"
    )

    assert response.status_code == 409
    assert "Limite de 20 convites" in response.json()["detail"]


def test_worker_who_never_worked_with_the_company_cannot_be_invited():
    company = make_company()
    vacancy = open_vacancy(company)

    response = client_for(owner(company)).post(
        f"/api/vacancies/{vacancy.pk}/invite/", {"worker_id": make_worker().pk}, format="json"
    )

    assert response.status_code == 404


def test_other_company_cannot_list_or_invite_for_the_vacancy():
    company, other = make_company(), make_company()
    worker = make_worker()
    paid_with(company, worker)
    vacancy = open_vacancy(company)
    client = client_for(owner(other))

    assert client.get(f"/api/company/past-workers/?vacancy={vacancy.pk}").status_code == 404
    response = client.post(
        f"/api/vacancies/{vacancy.pk}/invite/", {"worker_id": worker.pk}, format="json"
    )
    assert response.status_code == 404
