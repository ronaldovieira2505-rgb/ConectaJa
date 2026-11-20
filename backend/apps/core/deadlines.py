"""Processamento de prazos: aplica todas as transições por prazo, de forma idempotente."""

import logging
from datetime import timedelta

from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.vacancies import arrival, overtime, reminders
from apps.vacancies import assignment_services as assignments
from apps.vacancies import services as vacancies
from apps.vacancies.models import Assignment, Vacancy
from apps.workers.models import Worker
from integrations.payments import PaymentGatewayError

logger = logging.getLogger(__name__)

V = Vacancy.Status
S = Assignment.Status


def _apply(counter, key, queryset, action):
    """Aplica `action` a cada item; um item com problema não interrompe os demais."""
    for item in queryset:
        try:
            action(item)
        except (DomainError, PaymentGatewayError) as exc:
            logger.warning("Prazo não aplicado em %s#%s: %s", key, item.pk, exc)
            continue
        counter[key] = counter.get(key, 0) + 1


def process_deadlines(now=None):
    """Devolve um dicionário {ação: quantidade} do que foi aplicado nesta execução."""
    now = now or timezone.now()
    p = PlatformParameters.get()
    done = {}

    # 1. Vaga não paga: prazo para pagar expirou ou a antecedência mínima deixou de ser possível.
    unpaid = Vacancy.objects.filter(status=V.AWAITING_PAYMENT).filter(
        Q(created_at__lte=now - timedelta(minutes=p.payment_deadline_minutes))
        | Q(starts_at__lt=now + timedelta(minutes=p.min_publish_lead_minutes))
    )
    _apply(
        done,
        "vagas_canceladas_por_falta_de_pagamento",
        unpaid,
        lambda v: vacancies.cancel_unpaid_vacancy(
            v, reason="Prazo para pagamento expirado", now=now
        ),
    )

    # 2. Encerrar candidaturas.
    to_close = Vacancy.objects.filter(
        status=V.PUBLISHED,
        starts_at__lte=now + timedelta(minutes=p.applications_close_minutes_before),
    )
    _apply(
        done,
        "candidaturas_encerradas",
        to_close,
        lambda v: vacancies.close_applications(v, now=now),
    )

    # 3. Iniciar ou cancelar vagas cujo horário chegou.
    due = Vacancy.objects.filter(status=V.APPLICATIONS_CLOSED, starts_at__lte=now)
    with_people = due.filter(assignments__status__in=Assignment.ACTIVE_STATUSES).distinct()
    _apply(done, "vagas_iniciadas", with_people, lambda v: vacancies.start_vacancy(v, now=now))
    without_people = due.exclude(pk__in=with_people.values("pk"))
    _apply(
        done,
        "vagas_canceladas_sem_alocacao",
        without_people,
        lambda v: vacancies.cancel_vacancy_without_assignments(v, now=now),
    )

    # 4. Lembrete do turno ao prestador (US49). Só avisa: não muda estado nenhum.
    sent = reminders.send_due_reminders(now=now, params=p)
    if sent:
        done["lembretes"] = sent

    # 5. Justificativa de chegada sem resposta da empresa até o fim do turno → admin (US51).
    escalated = arrival.escalate_overdue(now=now)
    if escalated:
        done["justificativas_para_admin"] = escalated

    # 6. Falta (suspensão automática é efeito colateral e fica registrada em StateTransition).
    # Um pedido de justificativa em análise (empresa ou admin) não vira falta automática (US51).
    no_shows = Assignment.objects.filter(
        status=S.CONFIRMED,
        vacancy__starts_at__lt=now - timedelta(minutes=p.no_show_tolerance_minutes),
    ).exclude(arrival_justification__status__in=arrival.OPEN_STATUSES)
    def register_no_show(assignment):
        before = Worker.objects.get(pk=assignment.worker_id).suspended_until
        assignments.mark_no_show(assignment, now=now)
        after = Worker.objects.get(pk=assignment.worker_id).suspended_until
        if after != before:
            done["suspensoes_automaticas"] = done.get("suspensoes_automaticas", 0) + 1

    _apply(done, "faltas", no_shows, register_no_show)

    # 7. Pedido de hora extra sem resposta (US52): expira e nada é cobrado.
    _apply(
        done,
        "horas_extras_expiradas",
        overtime.overdue(now),
        lambda r: overtime.expire(r, now=now),
    )

    # 8. Check-out automático.
    # O fim é o da vaga ou o estendido pela hora extra aceita (US53).
    overdue = Assignment.objects.annotate(
        effective_end=Coalesce("extended_until", "vacancy__ends_at")
    ).filter(
        status=S.IN_PROGRESS,
        effective_end__lt=now - timedelta(minutes=p.auto_checkout_minutes_after_end),
    )
    _apply(done, "checkouts_automaticos", overdue, lambda a: assignments.auto_check_out(a, now=now))

    # 9. Aprovação automática por decurso da janela de contestação.
    silent = Assignment.objects.filter(
        status=S.AWAITING_VALIDATION,
        check_out_at__lte=now - timedelta(minutes=p.contest_window_minutes),
    )
    _apply(
        done, "aprovacoes_automaticas", silent, lambda a: assignments.auto_approve_hours(a, now=now)
    )

    # 10. Liquidação.
    _apply(
        done,
        "liquidacoes",
        Assignment.objects.filter(status=S.APPROVED),
        lambda a: assignments.settle(a, now=now),
    )

    # 11. Finalização das vagas.
    # Só as que já podem fechar: uma vaga com turno à espera de validação não é erro, e
    # tentar finalizá-la a cada execução só enchia o log de avisos.
    in_progress = [
        vacancy
        for vacancy in Vacancy.objects.filter(status=V.IN_PROGRESS).filter(
            Q(reopened=False) | Q(ends_at__lte=now)
        )
        if vacancies.can_finalize(vacancy, now)
    ]
    _apply(
        done, "vagas_finalizadas", in_progress, lambda v: vacancies.finalize_vacancy(v, now=now)
    )

    return done

