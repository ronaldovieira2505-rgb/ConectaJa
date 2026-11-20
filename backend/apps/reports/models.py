from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Report(models.Model):
    """Denúncia de uma vaga ou empresa feita por um prestador (US69). Analisada pelo admin."""

    class Target(models.TextChoices):
        VACANCY = "VAGA", "Vaga"
        COMPANY = "EMPRESA", "Empresa"

    class Reason(models.TextChoices):
        FAKE_VACANCY = "VAGA_FALSA", "Vaga falsa ou golpe"
        SIDE_PAYMENT = "PAGAMENTO_POR_FORA", "Pedido de pagamento por fora"
        DIFFERENT_CONDITIONS = "CONDICOES_DIFERENTES", "Condições diferentes do anúncio"
        BEHAVIOR = "COMPORTAMENTO", "Comportamento inadequado"
        OTHER = "OUTRO", "Outro"

    class Status(models.TextChoices):
        OPEN = "ABERTA", "Aberta"
        REVIEWING = "EM_ANALISE", "Em análise"
        UPHELD = "PROCEDENTE", "Procedente"
        DISMISSED = "IMPROCEDENTE", "Improcedente"

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
    target_type = models.CharField("tipo do alvo", max_length=10, choices=Target.choices)
    # Empresa denunciada: o alvo, ou a dona da vaga denunciada.
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.PROTECT,
        related_name="reports_received",
        verbose_name="empresa",
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
        ]

    def __str__(self):
        return f"Denúncia #{self.pk}"

    @property
    def target_label(self):
        if self.target_type == self.Target.VACANCY and self.vacancy_id:
            return f"Vaga “{self.vacancy.title}” ({self.company})"
        return f"Empresa {self.company}"
