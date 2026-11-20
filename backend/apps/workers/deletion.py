"""Exclusão da conta do prestador a pedido do titular (US11, LGPD).

Anonimiza os dados pessoais e apaga documentos e selfie. Mantém alocações, livro-razão,
avaliações e transições, que passam a apontar para "Prestador removido" (sem identificação
direta), como pede `docs/guia-do-repositorio.md`.
"""

from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import StateTransition
from apps.workers.models import Worker

REMOVED_NAME = "Prestador removido"
# Data de nascimento é obrigatória no banco: fica um valor fixo, sem identificação.
REMOVED_BIRTH_DATE = date(1900, 1, 1)
DELETION_REASON = "Solicitação do titular"
IN_PROGRESS_MESSAGE = (
    "Você tem turnos em andamento. Conclua ou cancele antes de excluir a conta."
)


class WrongPassword(DomainError):
    pass


def blocking_statuses():
    # Importado aqui: vagas dependem de prestadores, não o contrário.
    from apps.vacancies.models import Assignment

    S = Assignment.Status
    return (S.CONFIRMED, S.IN_PROGRESS, S.AWAITING_VALIDATION, S.CONTESTED, S.APPROVED)


def removed_cpf(worker):
    """Valor único e sem identificação para o CPF (nunca é um CPF válido)."""
    return f"X{worker.pk:010d}"


def _withdraw_pending_applications(worker, actor, now):
    from apps.core.state_machine import transition
    from apps.vacancies.models import Application
    from apps.vacancies.state_machine import APPLICATION_MACHINE

    for application in worker.applications.filter(status=Application.Status.PENDING):
        transition(
            application,
            APPLICATION_MACHINE,
            Application.Status.WITHDRAWN,
            actor=actor,
            reason="Conta excluída a pedido do titular",
            now=now,
        )


def delete_worker_account(worker, *, password, now=None):
    """Confere a senha e os turnos em andamento, anonimiza e desativa a conta.

    Senha errada ou turno em andamento: lança erro e nada muda.
    """
    now = now or timezone.now()
    user = worker.user
    if not isinstance(password, str) or not user.check_password(password):
        raise WrongPassword("Senha incorreta.")
    with transaction.atomic():
        worker = Worker.objects.select_for_update().select_related("user").get(pk=worker.pk)
        user = worker.user
        if worker.assignments.filter(status__in=blocking_statuses()).exists():
            raise DomainError(IN_PROGRESS_MESSAGE)
        _withdraw_pending_applications(worker, user, now)

        files = [document.file for document in worker.documents.all()]
        worker.documents.all().delete()

        worker.full_name = REMOVED_NAME
        worker.cpf = removed_cpf(worker)
        worker.phone = ""
        worker.birth_date = REMOVED_BIRTH_DATE
        worker.pix_key_type = ""
        worker.pix_key = ""
        worker.home_latitude = None
        worker.home_longitude = None
        # Habilidades e resumo (US08): o resumo é texto livre e pode ter dados pessoais.
        worker.skills = []
        worker.bio = ""
        worker.save()

        user.username = f"prestador-removido-{user.pk}"
        user.email = ""
        user.first_name = ""
        user.last_name = ""
        user.is_active = False
        user.set_unusable_password()  # também encerra as outras sessões
        user.save()

        StateTransition.objects.create(
            entity_type="WorkerAccount",
            entity_id=worker.pk,
            from_state="ATIVA",
            to_state="EXCLUIDA",
            actor=user,
            reason=DELETION_REASON,
            created_at=now,
        )
        # Arquivos só saem do disco depois que o banco confirmou a exclusão.
        transaction.on_commit(lambda: [stored.delete(save=False) for stored in files])
    return worker
