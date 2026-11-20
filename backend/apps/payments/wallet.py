"""Carteira do prestador: visão calculada do livro-razão e das alocações (sem saldo gravado)."""

from datetime import timedelta

from django.db.models import Max, Sum

from apps.core.models import PlatformParameters
from apps.payments.models import LedgerEntry
from apps.vacancies import overtime
from apps.vacancies.models import Assignment

K = LedgerEntry.Kind
AS = Assignment.Status

# Alocações cujo valor ainda não foi repassado (o repasse move a alocação para PAGA).
RECEIVABLE_STATUSES = (AS.CONFIRMED, AS.IN_PROGRESS, AS.AWAITING_VALIDATION, AS.APPROVED)


def _expected_release(assignment, params):
    """Fim do turno + janela de contestação; None quando só falta a liquidação."""
    window = timedelta(minutes=params.contest_window_minutes)
    if assignment.status == AS.APPROVED:
        return None
    if assignment.status == AS.AWAITING_VALIDATION and assignment.check_out_at:
        return assignment.check_out_at + window
    return (assignment.extended_until or assignment.vacancy.ends_at) + window


def _shift_info(assignment):
    vacancy = assignment.vacancy
    return {
        "assignment_id": assignment.pk,
        "vacancy_id": vacancy.pk,
        "title": vacancy.title,
        "company_name": vacancy.company.trade_name or vacancy.company.legal_name,
        "starts_at": vacancy.starts_at.isoformat(),
        "ends_at": vacancy.ends_at.isoformat(),
    }


def wallet_for(worker):
    params = PlatformParameters.get()

    receivable = []
    assignments = (
        Assignment.objects.filter(worker=worker, status__in=RECEIVABLE_STATUSES)
        .select_related("vacancy__company")
        .prefetch_related("overtime_requests")
        .order_by("vacancy__starts_at", "pk")
    )
    for assignment in assignments:
        expected = _expected_release(assignment, params)
        net = params.worker_net_cents(assignment.vacancy.pay_per_person_cents)
        extension = overtime.accepted_request(assignment)
        if extension:  # a hora extra tem a própria taxa (US53)
            net += params.worker_net_cents(extension.amount_cents)
        receivable.append(
            {
                **_shift_info(assignment),
                "status": assignment.status,
                "status_label": assignment.get_status_display(),
                "net_cents": net,
                "expected_release_at": expected.isoformat() if expected else None,
                "release_note": "" if expected else "após confirmação da empresa",
            }
        )

    entries = LedgerEntry.objects.filter(
        assignment__worker=worker, kind__in=(K.WORKER_PAYOUT, K.PLATFORM_FEE)
    )
    fees = {
        row["assignment_id"]: row["total"]
        for row in entries.filter(kind=K.PLATFORM_FEE)
        .values("assignment_id")
        .annotate(total=Sum("amount_cents"))
    }
    pix = worker.masked_pix_key
    released = []
    # Uma linha por turno: o repasse do turno e o da hora extra (US53) somados.
    payouts = (
        entries.filter(kind=K.WORKER_PAYOUT)
        .values("assignment_id")
        .annotate(total=Sum("amount_cents"), released_at=Max("created_at"))
        .order_by("-released_at", "-assignment_id")
    )
    shifts = Assignment.objects.select_related("vacancy__company").in_bulk(
        [row["assignment_id"] for row in payouts]
    )
    for row in payouts:
        fee = fees.get(row["assignment_id"], 0)
        released.append(
            {
                **_shift_info(shifts[row["assignment_id"]]),
                "released_at": row["released_at"].isoformat(),
                "gross_cents": row["total"] + fee,
                "fee_cents": fee,
                "net_cents": row["total"],
                "pix_destination": pix,
            }
        )

    return {
        "totals": {
            "receivable_cents": sum(i["net_cents"] for i in receivable),
            "released_cents": sum(i["net_cents"] for i in released),
            "fees_cents": sum(i["fee_cents"] for i in released),
        },
        "fee_percent": int(params.worker_fee_percent),
        "receivable": receivable,
        "released": released,
    }
