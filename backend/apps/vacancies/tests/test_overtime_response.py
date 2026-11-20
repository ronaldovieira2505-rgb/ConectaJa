"""US53: o prestador aceita (a empresa paga a extensão em custódia) ou recusa a hora extra."""

from datetime import date, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.deadlines import process_deadlines
from apps.core.exceptions import DomainError
from apps.core.models import Notification, PlatformParameters, StateTransition
from apps.core.tests.factories import LAT, LNG, make_admin, make_assignment, make_company
from apps.payments import services as payments
from apps.payments.models import Custody, LedgerEntry
from apps.payments.statement import statement_rows
from apps.payments.wallet import wallet_for
from apps.vacancies import assignment_services as assignments
from apps.vacancies import overtime
from apps.vacancies.history import financial_summary
from apps.vacancies.models import Assignment, OvertimeRequest

pytestmark = pytest.mark.django_db

OT = OvertimeRequest.Status
K = LedgerEntry.Kind


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def running_assignment(started_minutes_ago=60, hours=4):
    """Alocação EM_EXECUCAO: turno de `hours` h (R$ 100,00) que começou há pouco."""
    now = timezone.now()
    assignment = make_assignment(now=now, starts_in_hours=48)
    vacancy = assignment.vacancy
    vacancy.starts_at = now - timedelta(minutes=started_minutes_ago)
    vacancy.ends_at = vacancy.starts_at + timedelta(hours=hours)
    vacancy.save()
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=vacancy.starts_at)
    assignment.refresh_from_db()
    return assignment


def pending(assignment, minutes=60, amount_cents=3000):
    return overtime.request_overtime(assignment, minutes=minutes, amount_cents=amount_cents)


def respond(request, action, user=None):
    user = user or request.assignment.worker.user
    return client_for(user).post(f"/api/overtime/{request.pk}/{action}/")


def job(assignment):
    groups = client_for(assignment.worker.user).get("/api/workers/me/jobs/").json()["groups"]
    items = [i for g in groups.values() for i in g if i["kind"] == "assignment"]
    return next(i for i in items if i["id"] == assignment.pk)


def company_user(assignment):
    return assignment.vacancy.company.members.first().user


# Ver o pedido ------------------------------------------------------------------------------


def test_worker_sees_hours_gross_and_net_before_answering():
    assignment = running_assignment()
    pending(assignment, minutes=90, amount_cents=4000)
    item = job(assignment)
    assert item["can_respond_overtime"] is True
    assert item["overtime"]["minutes_label"] == "1 h 30 min"
    assert item["overtime"]["amount_cents"] == 4000
    assert item["overtime"]["net_cents"] == 3880  # 3% descontados
    assert item["extended_until"] is None


# Aceite -------------------------------------------------------------------------------------


def test_accept_pays_the_extension_into_custody_and_extends_the_shift():
    assignment = running_assignment()
    request = pending(assignment, minutes=60, amount_cents=3000)
    custody = assignment.vacancy.custody

    response = respond(request, "accept")
    assert response.status_code == 200
    assert response.json()["status"] == OT.ACCEPTED

    request.refresh_from_db()
    assert request.status == OT.ACCEPTED
    assert request.responded_at is not None
    assignment.refresh_from_db()
    assert assignment.extended_until == assignment.vacancy.ends_at + timedelta(hours=1)

    entry = LedgerEntry.objects.get(idempotency_key=f"overtime:{request.pk}:retencao")
    assert (entry.kind, entry.amount_cents, entry.assignment_id) == (
        K.RETENTION,
        3000,
        assignment.pk,
    )
    custody.refresh_from_db()
    assert custody.status == Custody.Status.HELD
    assert payments.retained_total(custody) == 10000 + 3000

    note = Notification.objects.get(user=company_user(assignment), title="Hora extra aceita")
    assert "R$ 30,00 foram retidos" in note.message
    assert StateTransition.objects.filter(
        entity_type="OvertimeRequest", entity_id=request.pk, to_state=OT.ACCEPTED
    ).exists()

    item = job(assignment)
    assert item["can_respond_overtime"] is False
    assert item["extended_until"] == assignment.extended_until.isoformat()
    # Uma extensão por alocação.
    with pytest.raises(DomainError, match="Só é possível uma extensão"):
        pending(assignment)


def test_payment_failure_keeps_the_request_pending_and_warns_both(fake_gateway):
    assignment = running_assignment()
    request = pending(assignment)
    fake_gateway.fail = True

    response = respond(request, "accept")
    assert response.status_code == 409
    assert "pagamento" in response.json()["detail"]
    request.refresh_from_db()
    assert request.status == OT.AWAITING
    assignment.refresh_from_db()
    assert assignment.extended_until is None
    assert not LedgerEntry.objects.filter(idempotency_key__startswith="overtime:").exists()
    assert Notification.objects.filter(
        user=assignment.worker.user, title="Não foi possível confirmar a hora extra"
    ).exists()
    assert Notification.objects.filter(
        user=company_user(assignment), title="Pagamento da hora extra falhou"
    ).exists()

    fake_gateway.fail = False  # o PSP voltou: dá para aceitar de novo dentro do prazo
    assert respond(request, "accept").status_code == 200


# Recusa -------------------------------------------------------------------------------------


def test_decline_has_no_penalty_and_nothing_is_charged():
    assignment = running_assignment()
    request = pending(assignment)
    response = respond(request, "decline")
    assert response.status_code == 200
    assert response.json()["status"] == OT.DECLINED

    request.refresh_from_db()
    assert request.status == OT.DECLINED
    note = Notification.objects.get(user=company_user(assignment), title="Hora extra recusada")
    assert "Nada foi cobrado" in note.message
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.IN_PROGRESS
    assert assignment.extended_until is None
    assert assignment.worker.suspended_until is None
    assert not LedgerEntry.objects.filter(idempotency_key__startswith="overtime:").exists()
    # Recusado: a empresa pode pedir de novo.
    assert overtime.can_request(assignment)


# Pedido encerrado e permissões --------------------------------------------------------------


@pytest.mark.parametrize("action", ["accept", "decline"])
def test_answered_or_expired_request_is_refused(action):
    assignment = running_assignment()
    request = pending(assignment)
    respond(request, "decline")
    assert respond(request, action).status_code == 409

    other = running_assignment()
    late = pending(other)
    OvertimeRequest.objects.filter(pk=late.pk).update(expires_at=timezone.now())
    response = respond(late, action)
    assert response.status_code == 409
    assert "expirou" in response.json()["detail"]


def test_expired_request_hides_the_buttons():
    assignment = running_assignment()
    request = pending(assignment)
    process_deadlines(now=request.expires_at)
    item = job(assignment)
    assert item["overtime"]["status"] == OT.EXPIRED
    assert item["can_respond_overtime"] is False
    assert respond(request, "accept").status_code == 409


def test_only_the_worker_of_the_assignment_answers():
    assignment = running_assignment()
    request = pending(assignment)
    other = running_assignment()
    assert respond(request, "accept", user=other.worker.user).status_code == 404
    assert respond(request, "accept", user=company_user(assignment)).status_code == 403
    request.refresh_from_db()
    assert request.status == OT.AWAITING


def test_cannot_accept_after_checking_out():
    assignment = running_assignment()
    request = pending(assignment)
    assignments.check_out(assignment)
    response = respond(request, "accept")
    assert response.status_code == 409
    assert "execução" in response.json()["detail"]


# Liquidação, invariante e carteira ----------------------------------------------------------


def _accepted(assignment, minutes=60, amount_cents=3000):
    request = pending(assignment, minutes=minutes, amount_cents=amount_cents)
    overtime.accept(request, actor=assignment.worker.user)
    assignment.refresh_from_db()
    return request


def test_settlement_pays_shift_and_extension_in_separate_entries():
    assignment = running_assignment()
    _accepted(assignment, amount_cents=3000)
    assignments.check_out(assignment)
    assignment.refresh_from_db()
    assignments.approve_hours(assignment)
    assignment.refresh_from_db()
    assignments.settle(assignment)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.PAID

    keys = dict(
        LedgerEntry.objects.filter(assignment=assignment).values_list(
            "idempotency_key", "amount_cents"
        )
    )
    pk = assignment.pk
    assert keys[f"assignment:{pk}:repasse"] == 9700
    assert keys[f"assignment:{pk}:taxa"] == 300
    assert keys[f"assignment:{pk}:repasse-extensao"] == 2910
    assert keys[f"assignment:{pk}:taxa-extensao"] == 90

    # Repetir a liquidação não duplica nada.
    payments.settle_assignment(assignment.vacancy.custody, assignment)
    assert LedgerEntry.objects.filter(assignment=assignment).count() == 5  # + retenção da extensão

    custody = assignment.vacancy.custody
    payments.close(custody)
    summary = financial_summary(assignment.vacancy)
    assert summary["retained_cents"] == 13000
    assert summary["balanced"] is True

    # Carteira e extrato: uma linha por turno, com a extensão somada.
    wallet = wallet_for(assignment.worker)
    [row] = wallet["released"]
    assert (row["gross_cents"], row["fee_cents"], row["net_cents"]) == (13000, 390, 12610)
    today = timezone.localdate()
    [line] = statement_rows(assignment.worker, date(today.year, 1, 1), today)
    assert (line.gross_cents, line.fee_cents, line.net_cents) == (13000, 390, 12610)


def test_wallet_receivable_includes_the_accepted_extension():
    assignment = running_assignment()
    _accepted(assignment, amount_cents=3000)
    [row] = wallet_for(assignment.worker)["receivable"]
    assert row["net_cents"] == 9700 + 2910


def test_refund_returns_the_extension_to_the_company():
    assignment = running_assignment()
    _accepted(assignment, amount_cents=3000)
    assignments.check_out(assignment)
    assignment.refresh_from_db()
    assignments.contest(assignment, reason="Não ficou o tempo combinado")
    assignment.refresh_from_db()
    assignments.resolve_contest(
        assignment, in_favor_of_worker=False, reason="Empresa tem razão", actor=make_admin()
    )
    refunds = LedgerEntry.objects.filter(assignment=assignment, kind=K.COMPANY_REFUND)
    assert sorted(refunds.values_list("amount_cents", flat=True)) == [3000, 10000]
    payments.close(assignment.vacancy.custody)
    assert financial_summary(assignment.vacancy)["balanced"] is True


def test_auto_check_out_uses_the_extended_end():
    assignment = running_assignment()
    _accepted(assignment, minutes=60)
    params = PlatformParameters.get()
    after = timedelta(minutes=params.auto_checkout_minutes_after_end + 1)

    process_deadlines(now=assignment.vacancy.ends_at + after)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.IN_PROGRESS

    process_deadlines(now=assignment.extended_until + after)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.AWAITING_VALIDATION
    assert assignment.check_out_at == assignment.extended_until


def test_company_review_shows_extended_end_and_total_value():
    assignment = running_assignment()
    _accepted(assignment, minutes=60, amount_cents=3000)
    assignments.check_out(assignment)
    pending_list = (
        client_for(company_user(assignment))
        .get("/api/company/assignments/pending/")
        .json()["results"]
    )
    [item] = pending_list
    assert item["gross_cents"] == 13000
    assert item["overtime_minutes"] == 60
    assert item["ends_at"] == assignment.extended_until.isoformat()


def test_company_team_shows_accepted_extension():
    assignment = running_assignment()
    _accepted(assignment)
    client = client_for(company_user(assignment))
    team = client.get(f"/api/vacancies/{assignment.vacancy_id}/candidates/").json()["team"]
    [member] = team
    assert member["overtime"]["status"] == OT.ACCEPTED
    assert member["can_request_overtime"] is False


def test_other_company_cannot_see_or_answer(fake_gateway):
    assignment = running_assignment()
    request = pending(assignment)
    outsider = make_company().members.first().user
    assert respond(request, "accept", user=outsider).status_code == 403
