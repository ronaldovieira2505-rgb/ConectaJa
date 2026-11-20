"""Denúncias (US69): o prestador denuncia uma vaga ou empresa suspeita.

A empresa denunciada não é avisada e nunca vê quem denunciou; só o admin analisa (US74).
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.companies.models import Company
from apps.core.exceptions import DomainError
from apps.core.notifications import notify_admins
from apps.core.state_machine import record_creation
from apps.reports.models import Report
from apps.reports.state_machine import REPORT_MACHINE
from apps.vacancies.models import Vacancy

T = Report.Target
DUPLICATE = "Você já tem uma denúncia aberta sobre este alvo. A equipe ainda está analisando."
SENT = "Denúncia enviada. A equipe vai analisar."


class TargetNotFound(DomainError):
    """Vaga ou empresa inexistente (ou que não é pública)."""


def clean(reason, description):
    if reason not in Report.Reason.values:
        raise DomainError("Escolha o motivo da lista.")
    if not isinstance(description, str):
        raise DomainError("Descreva o que aconteceu.")
    description = description.strip()
    if len(description) < Report.DESCRIPTION_MIN_LENGTH:
        raise DomainError("Descreva o que aconteceu com pelo menos 10 caracteres.")
    if len(description) > Report.DESCRIPTION_MAX_LENGTH:
        raise DomainError("A descrição pode ter no máximo 1.000 caracteres.")
    return reason, description


def _target(target_type, target_id):
    """(empresa, vaga) do alvo. Vaga ainda não paga não é pública e não pode ser denunciada."""
    if target_type == T.VACANCY:
        vacancy = (
            Vacancy.objects.select_related("company")
            .exclude(status=Vacancy.Status.AWAITING_PAYMENT)
            .filter(pk=target_id)
            .first()
        )
        if vacancy is None:
            raise TargetNotFound("Vaga não encontrada.")
        return vacancy.company, vacancy
    company = Company.objects.filter(pk=target_id).first()
    if company is None:
        raise TargetNotFound("Empresa não encontrada.")
    return company, None


def has_open_report(reporter, target_type, company, vacancy):
    reports = Report.objects.filter(
        reporter=reporter, target_type=target_type, status__in=Report.OPEN_STATUSES
    )
    if target_type == T.VACANCY:
        return reports.filter(vacancy=vacancy).exists()
    return reports.filter(company=company).exists()


@transaction.atomic
def report_vacancy_or_company(reporter, *, target_type, target_id, reason, description, now=None):
    """Registra a denúncia `ABERTA` e avisa os admins. Uma aberta por alvo e por pessoa."""
    now = now or timezone.now()
    if target_type not in (T.VACANCY, T.COMPANY):
        raise DomainError("Tipo de alvo inválido.")
    reason, description = clean(reason, description)
    company, vacancy = _target(target_type, target_id)
    if has_open_report(reporter, target_type, company, vacancy):
        raise DomainError(DUPLICATE)
    try:
        with transaction.atomic():
            report = Report.objects.create(
                reporter=reporter,
                target_type=target_type,
                company=company,
                vacancy=vacancy,
                reason=reason,
                description=description,
                created_at=now,
            )
    except IntegrityError:
        raise DomainError(DUPLICATE) from None
    record_creation(report, REPORT_MACHINE, actor=reporter, reason="Denúncia registrada", now=now)
    notify_admins(
        "DENUNCIA",
        "Nova denúncia",
        f"{report.target_label}: {report.get_reason_display()}.",
    )
    return report
