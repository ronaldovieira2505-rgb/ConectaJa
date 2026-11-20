from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Report(models.Model):
    """Denúncia de vaga ou empresa (prestador, US69) ou de prestador (empresa, US70).

    Analisada pelo admin (US74). O denunciado não é avisado e nunca vê quem denunciou.
    """

    class Target(models.TextChoices):
        VACANCY = "VAGA", "Vaga"
        COMPANY = "EMPRESA", "Empresa"
        WORKER = "PRESTADOR", "Prestador"

    class Reason(models.TextChoices):
        FAKE_VACANCY = "VAGA_FALSA", "Vaga falsa ou golpe"
        SIDE_PAYMENT = "PAGAMENTO_POR_FORA", "Pedido de pagamento por fora"
        DIFFERENT_CONDITIONS = "CONDICOES_DIFERENTES", "Condições diferentes do anúncio"
        BEHAVIOR = "COMPORTAMENTO", "Comportamento inadequado"
        DAMAGE = "DANO_FURTO", "Dano ou furto"
        HARASSMENT = "ASSEDIO", "Assédio"
        FAKE_ID = "DOCUMENTO_FALSO", "Documento ou identidade falsa"
        OTHER = "OUTRO", "Outro"

    class Status(models.TextChoices):
        OPEN = "ABERTA", "Aberta"
        REVIEWING = "EM_ANALISE", "Em análise"
        UPHELD = "PROCEDENTE", "Procedente"
        DISMISSED = "IMPROCEDENTE", "Improcedente"

    # Motivos que cada tipo de alvo aceita.
    COMPANY_REASONS = (
        Reason.FAKE_VACANCY,
        Reason.SIDE_PAYMENT,
        Reason.DIFFERENT_CONDITIONS,
        Reason.BEHAVIOR,
        Reason.OTHER,
    )
    WORKER_REASONS = (
        Reason.BEHAVIOR,
        Reason.DAMAGE,
        Reason.HARASSMENT,
        Reason.FAKE_ID,
        Reason.OTHER,
    )
    # Denúncia "aberta" para a regra de duplicidade: ainda não concluída pelo admin.
    OPEN_STATUSES = (Status.OPEN, Status.REVIEWING)
    DESCRIPTION_MIN_LENGTH = 10
    DESCRIPTION_MAX_LENGTH = 1000

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reports_made",
        verbose_name="quem denunciou",
    )
    # Empresa de quem denunciou um prestador (US70); vazio quando quem denuncia é prestador.
    reporter_company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reports_made",
        verbose_name="empresa que denunciou",
    )
    target_type = models.CharField("tipo do alvo", max_length=10, choices=Target.choices)
    # Empresa denunciada: o alvo, ou a dona da vaga denunciada (vazio na denúncia de prestador).
    company = models.ForeignKey(
        "companies.Company",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reports_received",
        verbose_name="empresa denunciada",
    )
    # Prestador denunciado e a alocação em que trabalhou para a empresa (US70).
    worker = models.ForeignKey(
        "workers.Worker",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reports_received",
        verbose_name="prestador denunciado",
    )
    assignment = models.ForeignKey(
        "vacancies.Assignment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reports",
        verbose_name="alocação",
    )
    vacancy = models.ForeignKey(
        "vacancies.Vacancy",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reports",
        verbose_name="vaga",
    )
    reason = models.CharField("motivo", max_length=25, choices=Reason.choices)
    description = models.TextField("descrição", max_length=DESCRIPTION_MAX_LENGTH)
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField("enviada em", default=timezone.now)
    decided_at = models.DateTimeField("concluída em", null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="concluída por",
    )
    decision = models.TextField("parecer", blank=True)

    class Meta:
        verbose_name = "denúncia"
        verbose_name_plural = "denúncias"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "vacancy"],
                condition=Q(target_type="VAGA", status__in=["ABERTA", "EM_ANALISE"]),
                name="one_open_vacancy_report_per_reporter",
            ),
            models.UniqueConstraint(
                fields=["reporter", "company"],
                condition=Q(target_type="EMPRESA", status__in=["ABERTA", "EM_ANALISE"]),
                name="one_open_company_report_per_reporter",
            ),
            models.UniqueConstraint(
                fields=["reporter_company", "assignment"],
                condition=Q(target_type="PRESTADOR", status__in=["ABERTA", "EM_ANALISE"]),
                name="one_open_worker_report_per_company_assignment",
            ),
        ]

    def __str__(self):
        return f"Denúncia #{self.pk}"

    @property
    def target_label(self):
        if self.target_type == self.Target.WORKER:
            return f"Prestador {self.worker.full_name} (alocação #{self.assignment_id})"
        if self.target_type == self.Target.VACANCY and self.vacancy_id:
            return f"Vaga “{self.vacancy.title}” ({self.company})"
        return f"Empresa {self.company}"
