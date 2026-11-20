"""US11 — exclusão da conta do prestador e anonimização dos dados (LGPD)."""

from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from apps.core.models import StateTransition
from apps.core.tests.factories import (
    LAT,
    LNG,
    NOW,
    make_assignment,
    make_company,
    make_published_vacancy,
    make_worker,
)
from apps.payments.models import LedgerEntry
from apps.vacancies import application_services as applications
from apps.vacancies import assignment_services as assignments
from apps.vacancies.models import Application, Assignment, Review
from apps.vacancies.review_services import company_rating
from apps.workers.deletion import IN_PROGRESS_MESSAGE, REMOVED_NAME
from apps.workers.models import Worker, WorkerDocument

pytestmark = pytest.mark.django_db

URL = "/api/workers/me/delete/"
PASSWORD = "senha-forte-123"  # senha das factories
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    return tmp_path / "private"


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def with_documents(worker):
    for kind in WorkerDocument.Kind:
        document = WorkerDocument(worker=worker, kind=kind)
        document.file.save(f"{kind.lower()}.png", ContentFile(PNG), save=True)
    return worker


def paid_assignment(worker):
    assignment = make_assignment(worker=worker)
    start = assignment.vacancy.starts_at
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)
    assignments.check_out(assignment, now=start + timedelta(hours=4))
    assignments.approve_hours(assignment, now=start + timedelta(hours=5))
    return assignments.settle(assignment, now=start + timedelta(hours=6))


def test_deletion_anonymizes_personal_data_and_keeps_financial_records(
    private_media, django_capture_on_commit_callbacks
):
    worker = with_documents(
        make_worker(phone="11988887777", skills=["LIMPEZA"], bio="Sou a Ana, moro na Sé.")
    )
    email, old_cpf = worker.user.email, worker.cpf
    paid = paid_assignment(worker)
    ledger_before = LedgerEntry.objects.count()
    client = client_for(worker.user)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(URL, {"password": PASSWORD}, format="json")

    assert response.status_code == 204
    worker.refresh_from_db()
    assert worker.full_name == REMOVED_NAME
    assert worker.cpf != old_cpf and not worker.cpf.isdigit()
    assert (worker.phone, worker.pix_key, worker.pix_key_type) == ("", "", "")
    assert worker.birth_date.year == 1900
    assert (worker.skills, worker.bio) == ([], "")
    user = worker.user
    assert (user.email, user.first_name, user.is_active) == ("", "", False)
    assert not user.has_usable_password()
    assert not WorkerDocument.objects.filter(worker=worker).exists()
    assert not list((private_media / "worker_documents").glob("*"))
    # Registros financeiros e de auditoria continuam.
    paid.refresh_from_db()
    assert paid.status == Assignment.Status.PAID and paid.worker_id == worker.pk
    assert LedgerEntry.objects.count() == ledger_before
    # Os identificadores ficam livres para um novo cadastro.
    assert not Worker.objects.filter(cpf=old_cpf).exists()
    assert not type(user).objects.filter(email__iexact=email).exists()


def test_after_deletion_the_session_ends_and_login_is_refused():
    worker = make_worker()
    email = worker.user.email
    client = client_for(worker.user)

    client.post(URL, {"password": PASSWORD}, format="json")

    assert client.get("/api/workers/me/").status_code == 403
    login = APIClient().post(
        "/api/auth/login/", {"email": email, "password": PASSWORD}, format="json"
    )
    assert login.status_code == 400


def test_pending_applications_become_withdrawn():
    worker = make_worker()
    vacancy = make_published_vacancy()
    application = applications.apply_to_vacancy(vacancy, worker, now=NOW)

    client_for(worker.user).post(URL, {"password": PASSWORD}, format="json")

    application.refresh_from_db()
    assert application.status == Application.Status.WITHDRAWN


def test_deletion_is_recorded_for_the_admin_without_personal_data():
    worker = make_worker()
    full_name, cpf = worker.full_name, worker.cpf

    client_for(worker.user).post(URL, {"password": PASSWORD}, format="json")

    entry = StateTransition.objects.get(entity_type="WorkerAccount", entity_id=worker.pk)
    assert (entry.from_state, entry.to_state) == ("ATIVA", "EXCLUIDA")
    assert entry.reason == "Solicitação do titular"
    assert full_name not in entry.reason and cpf not in entry.reason


def to_confirmed(assignment):
    return assignment


def to_in_progress(assignment):
    start = assignment.vacancy.starts_at
    return assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)


def to_awaiting_validation(assignment):
    assignment = to_in_progress(assignment)
    return assignments.check_out(assignment, now=assignment.vacancy.starts_at + timedelta(hours=4))


def to_approved(assignment):
    assignment = to_awaiting_validation(assignment)
    return assignments.approve_hours(assignment, now=assignment.check_out_at + timedelta(hours=1))


def to_contested(assignment):
    assignment = to_awaiting_validation(assignment)
    return assignments.contest(
        assignment, reason="Saiu antes", now=assignment.check_out_at + timedelta(minutes=5)
    )


@pytest.mark.parametrize(
    "advance", [to_confirmed, to_in_progress, to_awaiting_validation, to_approved, to_contested]
)
def test_shift_in_progress_blocks_deletion_and_nothing_changes(advance):
    worker = make_worker()
    advance(make_assignment(worker=worker))
    name = worker.full_name

    response = client_for(worker.user).post(URL, {"password": PASSWORD}, format="json")

    assert response.status_code == 409
    assert response.json()["detail"] == IN_PROGRESS_MESSAGE
    worker.refresh_from_db()
    assert worker.full_name == name and worker.user.is_active


def test_wrong_password_changes_nothing():
    worker = make_worker()
    name = worker.full_name

    response = client_for(worker.user).post(URL, {"password": "errada"}, format="json")

    assert response.status_code == 403
    assert response.json()["detail"] == "Senha incorreta."
    worker.refresh_from_db()
    assert worker.full_name == name and worker.user.is_active


def test_reviews_keep_counting_with_the_author_shown_as_removed():
    worker = make_worker()
    worker.full_name = "Ana Paula Ribeiro"
    worker.save(update_fields=["full_name"])
    paid = paid_assignment(worker)
    company = paid.vacancy.company
    Review.objects.create(
        assignment=paid,
        direction=Review.Direction.WORKER_TO_COMPANY,
        author=worker.user,
        rating=4,
    )

    client_for(worker.user).post(URL, {"password": PASSWORD}, format="json")

    assert company_rating(company.pk) == {"average": 4.0, "count": 1}
    company_user = company.members.first().user
    reviews = client_for(company_user).get("/api/company/reviews/").json()["results"]
    assert reviews[0]["reviewer"] == REMOVED_NAME


def test_company_cannot_use_the_endpoint():
    company_user = make_company().members.first().user

    response = client_for(company_user).post(URL, {"password": PASSWORD}, format="json")

    assert response.status_code == 403
