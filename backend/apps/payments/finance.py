"""Painel financeiro do admin (US77): retido, repassado, taxa, estornado e saldo retido.

Recorte do período: custódias cuja **retenção** (lançamento `RETENCAO`) caiu dentro do
intervalo. Para essas custódias somam-se **todos** os lançamentos, então o saldo e a
checagem da invariante (`RETENCAO = REPASSES + TAXAS + ESTORNOS`, docs/maquina-de-estados.md §4)
ficam completos. Os valores vêm do livro-razão; nada é calculado por fora dele.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.payments.models import Custody, LedgerEntry

K = LedgerEntry.Kind
DEFAULT_PERIOD_DAYS = 30


def format_money(cents):
    sign = "-" if cents < 0 else ""
    reais, rest = divmod(abs(cents), 100)
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{rest:02d}"


def default_period(now=None):
    """Últimos 30 dias, incluindo hoje: (início, fim) em datas."""
    today = timezone.localdate(now or timezone.now())
    return today - timedelta(days=DEFAULT_PERIOD_DAYS), today


def _bounds(start, end):
    tz = timezone.get_current_timezone()
    first = datetime.combine(start, time.min, tzinfo=tz)
    last = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
    return first, last


@dataclass
class FinanceRow:
    custody: Custody
    retained_cents: int = 0
    paid_out_cents: int = 0
    fees_cents: int = 0
    refunded_cents: int = 0

    @property
    def vacancy(self):
        return self.custody.vacancy

    @property
    def company(self):
        return self.custody.vacancy.company

    @property
    def balance_cents(self):
        return self.retained_cents - self.paid_out_cents - self.fees_cents - self.refunded_cents

    @property
    def diverged(self):
        """Custódia encerrada cuja soma não fecha."""
        return self.custody.status == Custody.Status.CLOSED and self.balance_cents != 0

    @property
    def status_display(self):
        return self.custody.get_status_display()

    @property
    def retained_display(self):
        return format_money(self.retained_cents)

    @property
    def paid_out_display(self):
        return format_money(self.paid_out_cents)

    @property
    def fees_display(self):
        return format_money(self.fees_cents)

    @property
    def refunded_display(self):
        return format_money(self.refunded_cents)

    @property
    def balance_display(self):
        return format_money(self.balance_cents)


@dataclass
class FinanceTotals:
    retained_cents: int = 0
    paid_out_cents: int = 0
    fees_cents: int = 0
    refunded_cents: int = 0

    @property
    def balance_cents(self):
        return self.retained_cents - self.paid_out_cents - self.fees_cents - self.refunded_cents

    retained_display = property(lambda self: format_money(self.retained_cents))
    paid_out_display = property(lambda self: format_money(self.paid_out_cents))
    fees_display = property(lambda self: format_money(self.fees_cents))
    refunded_display = property(lambda self: format_money(self.refunded_cents))
    balance_display = property(lambda self: format_money(self.balance_cents))


def compute_finance(start, end, *, company_id=None):
    """Totais e linhas por vaga para o período (datas inclusivas). Devolve `(totals, rows)`."""
    first, last = _bounds(start, end)
    in_period = LedgerEntry.objects.filter(
        kind=K.RETENTION, created_at__gte=first, created_at__lt=last
    ).values("custody_id")
    custodies = Custody.objects.filter(pk__in=in_period).select_related("vacancy__company")
    if company_id:
        custodies = custodies.filter(vacancy__company_id=company_id)
    custodies = custodies.order_by("-vacancy__starts_at", "pk")

    sums = {
        (row["custody_id"], row["kind"]): row["total"]
        for row in LedgerEntry.objects.filter(custody__in=custodies)
        .values("custody_id", "kind")
        .annotate(total=Sum("amount_cents"))
    }
    rows = []
    totals = FinanceTotals()
    for custody in custodies:

        def amount(kind, custody=custody):
            return sums.get((custody.pk, kind), 0)

        row = FinanceRow(
            custody=custody,
            retained_cents=amount(K.RETENTION),
            paid_out_cents=amount(K.WORKER_PAYOUT),
            fees_cents=amount(K.PLATFORM_FEE),
            refunded_cents=amount(K.COMPANY_REFUND),
        )
        rows.append(row)
        totals.retained_cents += row.retained_cents
        totals.paid_out_cents += row.paid_out_cents
        totals.fees_cents += row.fees_cents
        totals.refunded_cents += row.refunded_cents
    return totals, rows
