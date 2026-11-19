from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import PlatformParameters
from apps.workers.models import private_storage


class Vacancy(models.Model):
    """Vaga: um turno com N posições."""

    class Status(models.TextChoices):
        AWAITING_PAYMENT = "AGUARDANDO_PAGAMENTO", "Aguardando pagamento"
        PUBLISHED = "PUBLICADA", "Publicada"
        APPLICATIONS_CLOSED = "CANDIDATURAS_ENCERRADAS", "Candidaturas encerradas"
        IN_PROGRESS = "EM_ANDAMENTO", "Em andamento"
        FINISHED = "FINALIZADA", "Finalizada"
        CANCELLED = "CANCELADA", "Cancelada"

    class Category(models.TextChoices):
        CONSTRUCTION = "AJUDANTE_OBRA", "Ajudante de obra"
        LOADING = "CARGA_DESCARGA", "Carga e descarga"
        RETAIL = "VAREJO", "Varejo"
        EVENTS = "EVENTOS", "Eventos"
        PHOTOGRAPHY = "FOTOGRAFIA", "Fotografia"
        CLEANING = "LIMPEZA", "Limpeza"
        OTHER = "OUTROS", "Outros"

    company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, related_name="vacancies"
    )
    title = models.CharField("título", max_length=150)
    category = models.CharField("categoria", max_length=20, choices=Category.choices)
    description = models.TextField("escopo do serviço")
    street = models.CharField("logradouro", max_length=200, blank=True)
    number = models.CharField("número", max_length=20, blank=True)
    complement = models.CharField("complemento", max_length=100, blank=True)
    district = models.CharField("bairro", max_length=100, blank=True)
    city = models.CharField("cidade", max_length=100, blank=True)
    state = models.CharField("UF", max_length=2, blank=True)
    zip_code = models.CharField("CEP", max_length=8, blank=True)
    latitude = models.DecimalField("latitude", max_digits=9, decimal_places=6)
    longitude = models.DecimalField("longitude", max_digits=9, decimal_places=6)
    starts_at = models.DateTimeField("início")
    ends_at = models.DateTimeField("fim")
    pay_per_person_cents = models.PositiveIntegerField(
        "valor bruto por pessoa (centavos)", validators=[MinValueValidator(100)]
    )
    positions = models.PositiveIntegerField("posições", validators=[MinValueValidator(1)])
    requires_meeting = models.BooleanField("exige reunião [pós-MVP]", default=False)
    status = models.CharField(
        "status", max_length=30, choices=Status.choices, default=Status.AWAITING_PAYMENT
    )
    reopened = models.BooleanField("reaberta por falta", default=False)
    auto_call_waitlist = models.BooleanField(
        "chamar automaticamente da lista de espera", default=True
    )
    photo = models.FileField(
        "foto do local", upload_to="vacancy_photos/", storage=private_storage, blank=True
    )
    created_at = models.DateTimeField("criada em", default=timezone.now)

    class Meta:
        verbose_name = "vaga"
        verbose_name_plural = "vagas"
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="vacancy_end_after_start"
            ),
            models.CheckConstraint(condition=Q(positions__gte=1), name="vacancy_positions_gte_1"),
        ]

    def __str__(self):
        return f"{self.title} (#{self.pk})"

    @property
    def filled_positions(self):
        return self.assignments.filter(status__in=Assignment.ACTIVE_STATUSES).count()

    @property
    def unavailable_positions(self):
        """Posições ocupadas ou canceladas pela empresa (não voltam a ser ofertadas)."""
        return self.assignments.filter(status__in=Assignment.UNAVAILABLE_STATUSES).count()

    @property
    def worker_net_cents(self):
        return PlatformParameters.get().worker_net_cents(self.pay_per_person_cents)

    def accepts_applications(self, now):
        if self.status == self.Status.PUBLISHED:
            close_minutes = PlatformParameters.get().applications_close_minutes_before
            if now < self.starts_at - timedelta(minutes=close_minutes):
                return True
            return self.reopened and now < self.ends_at
        return (
            self.reopened
            and now < self.ends_at
            and self.status
            in (self.Status.APPLICATIONS_CLOSED, self.Status.IN_PROGRESS)
        )


class VacancyChange(models.Model):
    """Auditoria das edições de campos da vaga (quem, quando, campo, antes, depois)."""

    vacancy = models.ForeignKey(Vacancy, on_delete=models.CASCADE, related_name="changes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="usuário",
    )
    changed_at = models.DateTimeField("data", default=timezone.now)
    field = models.CharField("campo", max_length=40)
    old_value = models.TextField("valor anterior", blank=True)
    new_value = models.TextField("valor novo", blank=True)

    class Meta:
        verbose_name = "alteração de vaga"
        verbose_name_plural = "alterações de vagas"
        ordering = ["-changed_at", "-pk"]

    def __str__(self):
        return f"{self.field} da vaga #{self.vacancy_id}"


class Application(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDENTE", "Pendente"
        APPROVED = "APROVADA", "Aprovada"
        REJECTED = "RECUSADA", "Recusada"
        WITHDRAWN = "DESISTENCIA", "Desistência"
        EXPIRED = "EXPIRADA", "Expirada"

    vacancy = models.ForeignKey(Vacancy, on_delete=models.CASCADE, related_name="applications")
    worker = models.ForeignKey(
        "workers.Worker", on_delete=models.CASCADE, related_name="applications"
    )
    status = models.CharField("status", max_length=12, choices=Status.choices, default="PENDENTE")
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    decided_at = models.DateTimeField("decidida em", null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="decidida por",
    )

    class Meta:
        verbose_name = "candidatura"
        verbose_name_plural = "candidaturas"
        constraints = [
            models.UniqueConstraint(fields=["vacancy", "worker"], name="unique_application")
        ]

    def __str__(self):
        return f"Candidatura #{self.pk}"


class Assignment(models.Model):
    """Alocação: o turno de um prestador."""

    class Status(models.TextChoices):
        CONFIRMED = "CONFIRMADA", "Confirmada"
        IN_PROGRESS = "EM_EXECUCAO", "Em execução"
        AWAITING_VALIDATION = "AGUARDANDO_VALIDACAO", "Aguardando validação"
        CONTESTED = "CONTESTADA", "Contestada"
        APPROVED = "APROVADA", "Aprovada"
        PAID = "PAGA", "Paga"
        NO_SHOW = "FALTA", "Falta"
        REFUNDED = "ESTORNADA", "Estornada"
        CANCELLED_BY_WORKER = "CANCELADA_PRESTADOR", "Cancelada pelo prestador"
        CANCELLED_BY_COMPANY = "CANCELADA_EMPRESA", "Cancelada pela empresa"

    # Alocações que ocupam uma posição da vaga.
    ACTIVE_STATUSES = (
        Status.CONFIRMED,
        Status.IN_PROGRESS,
        Status.AWAITING_VALIDATION,
        Status.CONTESTED,
        Status.APPROVED,
        Status.PAID,
    )

    # Posições indisponíveis: as ativas e as que a empresa cancelou (desistiu da posição,
    # então ela não volta para a busca nem para novas aprovações).
    UNAVAILABLE_STATUSES = (*ACTIVE_STATUSES, Status.CANCELLED_BY_COMPANY)

    vacancy = models.ForeignKey(Vacancy, on_delete=models.CASCADE, related_name="assignments")
    worker = models.ForeignKey(
        "workers.Worker", on_delete=models.CASCADE, related_name="assignments"
    )
    application = models.OneToOneField(
        Application, on_delete=models.PROTECT, related_name="assignment"
    )
    status = models.CharField("status", max_length=20, choices=Status.choices, default="CONFIRMADA")
    check_in_at = models.DateTimeField("check-in", null=True, blank=True)
    check_in_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_in_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_in_distance_m = models.PositiveIntegerField(
        "distância no check-in (m)", null=True, blank=True
    )
    check_out_at = models.DateTimeField("check-out", null=True, blank=True)
    check_out_auto = models.BooleanField("check-out automático", default=False)
    validated_at = models.DateTimeField("validada em", null=True, blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="validada por",
        help_text="Vazio com data de validação = SISTEMA.",
    )
    contest_response = models.TextField(
        "resposta do prestador à contestação",
        blank=True,
        help_text="Resposta única e definitiva (US58).",
    )
    contest_response_at = models.DateTimeField(
        "resposta à contestação enviada em", null=True, blank=True
    )

    CONTEST_RESPONSE_MIN_LENGTH = 10
    CONTEST_RESPONSE_MAX_LENGTH = 1000

    class Meta:
        verbose_name = "alocação"
        verbose_name_plural = "alocações"

    def __str__(self):
        return f"Alocação #{self.pk}"


class Review(models.Model):
    """Avaliação de uma alocação (US63: empresa → prestador; reutilizável pela US64)."""

    class Direction(models.TextChoices):
        COMPANY_TO_WORKER = "EMPRESA_PARA_PRESTADOR", "Empresa avalia o prestador"
        WORKER_TO_COMPANY = "PRESTADOR_PARA_EMPRESA", "Prestador avalia a empresa"

    COMMENT_MAX_LENGTH = 500

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="reviews")
    direction = models.CharField("sentido", max_length=22, choices=Direction.choices)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="autor",
    )
    rating = models.PositiveSmallIntegerField(
        "nota",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.CharField("comentário", max_length=COMMENT_MAX_LENGTH, blank=True)
    created_at = models.DateTimeField("criada em", default=timezone.now)

    class Meta:
        verbose_name = "avaliação"
        verbose_name_plural = "avaliações"
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "direction"], name="unique_review_per_direction"
            ),
            models.CheckConstraint(
                condition=Q(rating__gte=1, rating__lte=5), name="review_rating_1_to_5"
            ),
        ]

    def __str__(self):
        return f"Avaliação #{self.pk} ({self.rating}★)"
