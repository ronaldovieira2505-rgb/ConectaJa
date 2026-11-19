"""Indicadores operacionais do admin (US78): preenchimento das vagas e índice de faltas.

Recorte do período: vagas **publicadas** (pagas) dentro do intervalo, pela data da
transição para `PUBLICADA` (`StateTransition`). Todas as alocações dessas vagas nasceram
`CONFIRMADA`, então "posições preenchidas" = alocações criadas. Valores vêm do livro-razão.
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.core.models import StateTransition
from apps.payments.models import LedgerEntry
from apps.vacancies.models import Assignment, Vacancy

DEFAULT_PERIOD_DAYS = 30
EMPTY = "—"

# Alocações que nunca chegaram ao horário de início por terem sido canceladas antes.
CANCELLED_STATUSES = (
    Assignment.Status.CANCELLED_BY_WORKER,
    Assignment.Status.CANCELLED_BY_COMPANY,
)


@dataclass
class Indicators:
    published_vacancies: int = 0
    positions: int = 0
    filled_positions: int = 0
    reached_start: int = 0
    no_shows: int = 0
    paid_shifts: int = 0
    gross_moved_cents: int = 0
    platform_fee_cents: int = 0
    refund_count: int = 0
    refund_cents: int = 0
    fill_rate: Decimal | None = field(default=None)
    no_show_rate: Decimal | None = field(default=None)

    @property
    def fill_rate_display(self):
        return format_percent(self.fill_rate)

    @property
    def no_show_rate_display(self):
        return format_percent(self.no_show_rate)

    @property
    def gross_moved_display(self):
        return format_money(self.gross_moved_cents)

    @property
    def platform_fee_display(self):
        return format_money(self.platform_fee_cents)

    @property
    def refund_display(self):
        return format_money(self.refund_cents)


def percent(part, total):
    """Percentual com uma casa decimal; `None` quando não há base (sem divisão por zero)."""
    if not total:
        return None
    value = Decimal(part) * 100 / Decimal(total)
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def format_percent(value):
    return EMPTY if value is None else f"{str(value).replace('.', ',')}%"


def format_money(cents):
    reais, rest = divmod(cents, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{rest:02d}"


def default_period(now=None):
    """Últimos 30 dias, incluindo hoje: (início, fim) em datas."""
    today = timezone.localdate(now or timezone.now())
    return today - timedelta(days=DEFAULT_PERIOD_DAYS), today


def _bounds(start, end):
    """Datas (fuso America/Sao_Paulo) → intervalo [início, fim) em datetimes aware."""
    tz = timezone.get_current_timezone()
    first = datetime.combine(start, time.min, tzinfo=tz)
    last = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
    return first, last


def published_vacancy_ids(start, end):
    first, last = _bounds(start, end)
    return StateTransition.objects.filter(
        entity_type="Vacancy",
        to_state=Vacancy.Status.PUBLISHED,
        created_at__gte=first,
        created_at__lt=last,
    ).values("entity_id")


def _compute(vacancies, now):
    result = Indicators()
    result.published_vacancies = vacancies.count()
    result.positions = vacancies.aggregate(total=Sum("positions"))["total"] or 0

    assignments = Assignment.objects.filter(vacancy__in=vacancies)
    result.filled_positions = assignments.count()
    started = assignments.filter(vacancy__starts_at__lte=now).exclude(
        status__in=CANCELLED_STATUSES
    )
    result.reached_start = started.count()
    result.no_shows = started.filter(status=Assignment.Status.NO_SHOW).count()
    result.paid_shifts = assignments.filter(status=Assignment.Status.PAID).count()

    entries = LedgerEntry.objects.filter(custody__vacancy__in=vacancies)
    sums = {
        row["kind"]: row
        for row in entries.values("kind").annotate(total=Sum("amount_cents"), n=Count("id"))
    }

    def total(kind):
        return sums.get(kind, {}).get("total") or 0

    result.platform_fee_cents = total(LedgerEntry.Kind.PLATFORM_FEE)
    result.gross_moved_cents = total(LedgerEntry.Kind.WORKER_PAYOUT) + result.platform_fee_cents
    result.refund_cents = total(LedgerEntry.Kind.COMPANY_REFUND)
    result.refund_count = sums.get(LedgerEntry.Kind.COMPANY_REFUND, {}).get("n") or 0

    result.fill_rate = percent(result.filled_positions, result.positions)
    result.no_show_rate = percent(result.no_shows, result.reached_start)
    return result


def compute_indicators(start, end, *, category=None, now=None):
    """Indicadores gerais e por categoria para o período (datas inclusivas)."""
    now = now or timezone.now()
    vacancies = Vacancy.objects.filter(pk__in=published_vacancy_ids(start, end))
    if category:
        vacancies = vacancies.filter(category=category)
    overall = _compute(vacancies, now)
    categories = [c for c in Vacancy.Category if not category or c.value == category]
    by_category = [
        (label, _compute(vacancies.filter(category=value), now))
        for value, label in ((c.value, c.label) for c in categories)
    ]
    return overall, by_category
