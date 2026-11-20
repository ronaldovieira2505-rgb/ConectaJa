"""Suspensão e reativação manual de conta pelo admin (US76).

Vale para prestador (`Worker`) e empresa (`Company`). A suspensão automática por faltas (US55)
usa o mesmo campo `suspended_until`; a reativação encerra qualquer uma das duas.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.companies.models import Company
from apps.core.exceptions import DomainError
from apps.core.models import StateTransition
from apps.core.notifications import notify, notify_company
from apps.workers.models import Worker

MIN_DAYS = 1
MAX_DAYS = 365
ACTIVE, SUSPENDED = "ATIVO", "SUSPENSO"

ENTITY_TYPES = {Worker: "WorkerSuspension", Company: "CompanySuspension"}


class SuspensionNotAllowed(DomainError):
    """Só admin suspende ou reativa contas."""


def _require_admin(actor):
    if actor is None or not actor.is_authenticated or actor.role != Role.ADMIN:
        raise SuspensionNotAllowed("Só o admin pode suspender ou reativar contas.")


def _require_reason(reason):
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("O motivo é obrigatório.")
    return reason


def _lock(subject):
    return type(subject)._default_manager.select_for_update().get(pk=subject.pk)


def _notify(subject, title, message):
    if isinstance(subject, Worker):
        notify(subject.user, "SUSPENSAO", title, message)
    else:
        notify_company(subject, "SUSPENSAO", title, message)


def _until_text(subject):
    if subject.suspension_indefinite:
        return "por tempo indeterminado"
    local = subject.suspended_until.astimezone(ZoneInfo("America/Sao_Paulo"))
    return f"até {local:%d/%m/%Y}"


@transaction.atomic
def suspend_account(subject, *, actor, reason, days=None, indefinite=False, now=None):
    """Suspende por `days` (1 a 365) ou por tempo indeterminado. Audita e notifica."""
    now = now or timezone.now()
    _require_admin(actor)
    reason = _require_reason(reason)
    if indefinite:
        if days is not None:
            raise DomainError("Informe o número de dias ou tempo indeterminado, não os dois.")
    else:
        if isinstance(days, bool) or not isinstance(days, int):
            raise DomainError("Informe o número de dias (1 a 365) ou tempo indeterminado.")
        if not MIN_DAYS <= days <= MAX_DAYS:
            raise DomainError(f"O número de dias deve estar entre {MIN_DAYS} e {MAX_DAYS}.")
    subject = _lock(subject)
    if subject.is_suspended(now):
        raise DomainError("A conta já está suspensa.")
    subject.suspension_indefinite = indefinite
    subject.suspended_until = None if indefinite else now + timedelta(days=days)
    subject.save(update_fields=["suspension_indefinite", "suspended_until"])
    StateTransition.objects.create(
        entity_type=ENTITY_TYPES[type(subject)],
        entity_id=subject.pk,
        from_state=ACTIVE,
        to_state=SUSPENDED,
        actor=actor,
        reason=reason,
        created_at=now,
    )
    _notify(subject, "Conta suspensa", f"Conta suspensa {_until_text(subject)}. Motivo: {reason}")
    return subject


@transaction.atomic
def reactivate_account(subject, *, actor, reason, now=None):
    """Encerra na hora a suspensão (manual ou automática). Audita e notifica."""
    now = now or timezone.now()
    _require_admin(actor)
    reason = _require_reason(reason)
    subject = _lock(subject)
    if not subject.is_suspended(now):
        raise DomainError("A conta não está suspensa.")
    subject.suspension_indefinite = False
    subject.suspended_until = None
    subject.save(update_fields=["suspension_indefinite", "suspended_until"])
    StateTransition.objects.create(
        entity_type=ENTITY_TYPES[type(subject)],
        entity_id=subject.pk,
        from_state=SUSPENDED,
        to_state=ACTIVE,
        actor=actor,
        reason=reason,
        created_at=now,
    )
    _notify(subject, "Conta reativada", f"Sua conta foi reativada. Motivo: {reason}")
    return subject
