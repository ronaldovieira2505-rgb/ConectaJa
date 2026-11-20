"""Análise das denúncias pelo admin (US74).

`ABERTA → EM_ANALISE → PROCEDENTE | IMPROCEDENTE` (também direto de `ABERTA` para a conclusão).
A conclusão exige parecer, fica auditada em `StateTransition` e avisa quem denunciou só do
resultado, sem detalhes sobre o outro lado.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.core.notifications import notify
from apps.core.state_machine import transition
from apps.reports.models import Report
from apps.reports.state_machine import REPORT_MACHINE
from apps.vacancies.models import Assignment, Review

R = Report.Status
T = Report.Target
# Alvo com esta quantidade de denúncias procedentes ganha um alerta no painel (decisão do PO).
UPHELD_ALERT_THRESHOLD = 3
# Denúncias não concluídas há mais tempo que isto são destacadas na lista.
OPEN_ALERT_AFTER = timedelta(hours=48)
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


class ReviewNotAllowed(DomainError):
    """Só o admin analisa denúncias."""


def _require_admin(actor):
    if actor is None or not actor.is_authenticated or actor.role != Role.ADMIN:
        raise ReviewNotAllowed("Só o admin analisa denúncias.")


def _lock(report):
    return Report.objects.select_for_update().get(pk=report.pk)


def is_overdue(report, now=None):
    """Ainda não concluída e aberta há mais de 48 h."""
    now = now or timezone.now()
    return report.status in Report.OPEN_STATUSES and now - report.created_at > OPEN_ALERT_AFTER


@transaction.atomic
def start_review(report, *, actor, now=None):
    """`ABERTA → EM_ANALISE`, registrado com o admin como autor."""
    _require_admin(actor)
    report = _lock(report)
    if report.status != R.OPEN:
        raise DomainError("Só uma denúncia aberta pode ser marcada como em análise.")
    return transition(
        report, REPORT_MACHINE, R.REVIEWING, actor=actor, reason="Denúncia em análise", now=now
    )


@transaction.atomic
def conclude(report, *, actor, upheld, decision, now=None):
    """Conclui como procedente ou improcedente. Parecer obrigatório; avisa quem denunciou."""
    now = now or timezone.now()
    _require_admin(actor)
    decision = (decision or "").strip() if isinstance(decision, str) or decision is None else ""
    if not decision:
        raise DomainError("O parecer é obrigatório.")
    report = _lock(report)
    if report.status not in Report.OPEN_STATUSES:
        raise DomainError("Esta denúncia já foi concluída.")
    target = R.UPHELD if upheld else R.DISMISSED
    report = transition(
        report,
        REPORT_MACHINE,
        target,
        actor=actor,
        reason=decision,
        now=now,
        decided_at=now,
        decided_by=actor,
        decision=decision,
    )
    sent = report.created_at.astimezone(LOCAL_TZ)
    result = "procedente" if upheld else "improcedente"
    notify(
        report.reporter,
        "DENUNCIA",
        "Sua denúncia foi analisada",
        f"A equipe concluiu a análise da denúncia que você enviou em {sent:%d/%m/%Y}: {result}. "
        "Obrigado por ajudar a manter a plataforma segura.",
    )
    return report


# Histórico do alvo ------------------------------------------------------------------------


def target_subject(report):
    """Conta que pode ser suspensa a partir da denúncia: o prestador ou a empresa."""
    return report.worker if report.target_type == T.WORKER else report.company


def reports_about(subject):
    """Todas as denúncias sobre o prestador ou a empresa (inclusive as de vagas dela)."""
    if subject is None:
        return Report.objects.none()
    if subject._meta.model_name == "worker":
        return Report.objects.filter(worker=subject)
    return Report.objects.filter(company=subject)


def upheld_count(subject):
    return reports_about(subject).filter(status=R.UPHELD).count()


def has_upheld_alert(subject):
    return upheld_count(subject) >= UPHELD_ALERT_THRESHOLD


def target_history(report):
    """Outras denúncias, faltas e avaliações do alvo, para o detalhe da denúncia."""
    subject = target_subject(report)
    others = reports_about(subject).exclude(pk=report.pk).order_by("-created_at", "-pk")
    upheld = upheld_count(subject)
    history = {
        "subject": subject,
        "other_reports": list(others[:20]),
        "upheld_count": upheld,
        "upheld_alert": upheld >= UPHELD_ALERT_THRESHOLD,
        "no_shows": None,
        "reviews": [],
        "rating": None,
    }
    if subject is None:
        return history
    if report.target_type == T.WORKER:
        history["no_shows"] = Assignment.objects.filter(
            worker=subject, status=Assignment.Status.NO_SHOW
        ).count()
        reviews = Review.objects.filter(
            assignment__worker=subject, direction=Review.Direction.COMPANY_TO_WORKER
        )
    else:
        reviews = Review.objects.filter(
            assignment__vacancy__company=subject, direction=Review.Direction.WORKER_TO_COMPANY
        )
    summary = reviews.aggregate(average=Avg("rating"), count=Count("id"))
    history["rating"] = summary if summary["count"] else None
    history["reviews"] = list(reviews.order_by("-created_at", "-pk")[:5])
    return history
