"""Linha do tempo completa de uma vaga (US75): somente leitura, para o admin.

Reúne as transições de estado (`StateTransition`) da vaga, das candidaturas, das alocações e da
custódia, as edições (`VacancyChange`) e os lançamentos do livro-razão, em ordem cronológica.
CPF e chave PIX aparecem sempre mascarados.
"""

from dataclasses import dataclass, field
from datetime import datetime

from django.db.models import Sum

from apps.accounts.models import Role
from apps.core.masking import mask_email
from apps.core.models import StateTransition
from apps.payments.models import Custody, LedgerEntry
from apps.vacancies.models import Application, Assignment, Vacancy, VacancyChange

K = LedgerEntry.Kind

_ENTITY_LABELS = {
    "Vacancy": "Vaga",
    "Application": "Candidatura",
    "Assignment": "Alocação",
    "Custody": "Custódia",
}

_STATE_LABELS = {
    "Vacancy": dict(Vacancy.Status.choices),
    "Application": dict(Application.Status.choices),
    "Assignment": dict(Assignment.Status.choices),
    "Custody": dict(Custody.Status.choices),
}


@dataclass
class HistoryEvent:
    at: datetime
    category: str
    actor: str
    description: str
    from_state: str = ""
    to_state: str = ""
    reason: str = ""
    detail: str = ""
    order: tuple = field(default=(0, 0))


def format_brl(cents):
    reais, centavos = divmod(cents, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def actor_label(user):
    """Empresa, Prestador, Admin ou SISTEMA (usuário vazio)."""
    if user is None:
        return "SISTEMA"
    if user.is_staff or user.role == Role.ADMIN:
        kind = "Admin"
    elif user.role == Role.COMPANY:
        kind = "Empresa"
    else:
        kind = "Prestador"
    return f"{kind} ({mask_email(user.email)})"


def _state_label(entity_type, state):
    if not state:
        return ""
    return _STATE_LABELS.get(entity_type, {}).get(state, state)


def _worker_label(worker):
    return f"{worker.full_name} (CPF {worker.masked_cpf})"


def _transition_events(vacancy):
    applications = {
        a.pk: a for a in Application.objects.filter(vacancy=vacancy).select_related("worker")
    }
    assignments = {
        a.pk: a for a in Assignment.objects.filter(vacancy=vacancy).select_related("worker")
    }
    custody = Custody.objects.filter(vacancy=vacancy).first()

    filters = [("Vacancy", [vacancy.pk]), ("Application", list(applications)),
               ("Assignment", list(assignments))]
    if custody:
        filters.append(("Custody", [custody.pk]))

    events = []
    for entity_type, ids in filters:
        if not ids:
            continue
        rows = StateTransition.objects.filter(
            entity_type=entity_type, entity_id__in=ids
        ).select_related("actor")
        for row in rows:
            subject = _ENTITY_LABELS[entity_type]
            detail = ""
            if entity_type == "Application":
                worker = applications[row.entity_id].worker
                subject += f" #{row.entity_id} — {_worker_label(worker)}"
            elif entity_type == "Assignment":
                assignment = assignments[row.entity_id]
                subject += f" #{row.entity_id} — {_worker_label(assignment.worker)}"
                if (
                    row.to_state == Assignment.Status.IN_PROGRESS
                    and assignment.check_in_distance_m is not None
                ):
                    detail = f"Check-in a {assignment.check_in_distance_m} m do local"
            events.append(
                HistoryEvent(
                    at=row.created_at,
                    category=_ENTITY_LABELS[entity_type],
                    actor=actor_label(row.actor),
                    description=subject,
                    from_state=_state_label(entity_type, row.from_state),
                    to_state=_state_label(entity_type, row.to_state),
                    reason=row.reason,
                    detail=detail,
                    order=(0, row.pk),
                )
            )
    return events


def _change_events(vacancy):
    return [
        HistoryEvent(
            at=change.changed_at,
            category="Edição",
            actor=actor_label(change.user),
            description=f"Edição do campo “{change.field}”",
            from_state=change.old_value,
            to_state=change.new_value,
            order=(1, change.pk),
        )
        for change in VacancyChange.objects.filter(vacancy=vacancy).select_related("user")
    ]


def _ledger_events(vacancy):
    entries = LedgerEntry.objects.filter(custody__vacancy=vacancy).select_related(
        "assignment__worker"
    )
    events = []
    for entry in entries:
        detail = format_brl(entry.amount_cents)
        description = f"Livro-razão: {entry.get_kind_display()}"
        if entry.assignment_id:
            description += f" — alocação #{entry.assignment_id}"
            if entry.kind == K.WORKER_PAYOUT:
                worker = entry.assignment.worker
                detail += f" para PIX {worker.masked_pix_key}"
        events.append(
            HistoryEvent(
                at=entry.created_at,
                category="Livro-razão",
                actor="SISTEMA",
                description=description,
                detail=detail,
                order=(2, entry.pk),
            )
        )
    return events


def financial_summary(vacancy):
    totals = {
        row["kind"]: row["total"]
        for row in LedgerEntry.objects.filter(custody__vacancy=vacancy)
        .values("kind")
        .annotate(total=Sum("amount_cents"))
    }
    retained = totals.get(K.RETENTION, 0)
    paid_out = totals.get(K.WORKER_PAYOUT, 0)
    fees = totals.get(K.PLATFORM_FEE, 0)
    refunded = totals.get(K.COMPANY_REFUND, 0)
    return {
        "retained_cents": retained,
        "paid_out_cents": paid_out,
        "fees_cents": fees,
        "refunded_cents": refunded,
        "retained_display": format_brl(retained),
        "paid_out_display": format_brl(paid_out),
        "fees_display": format_brl(fees),
        "refunded_display": format_brl(refunded),
        "balanced": retained == paid_out + fees + refunded,
    }


def build_history(vacancy):
    """Eventos em ordem cronológica (empates resolvidos por origem e id)."""
    events = _transition_events(vacancy) + _change_events(vacancy) + _ledger_events(vacancy)
    return sorted(events, key=lambda e: (e.at, e.order))
