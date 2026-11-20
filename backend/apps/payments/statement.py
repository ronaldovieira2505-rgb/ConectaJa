"""Extrato do prestador (US61): turnos pagos de um período, em CSV, a partir do livro-razão.

Usa os mesmos lançamentos da carteira (`REPASSE_PRESTADOR` e `TAXA_PLATAFORMA`), então os
números sempre batem com ela. O período recorta pela data do pagamento (horário de São Paulo).
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.payments.models import LedgerEntry

K = LedgerEntry.Kind

MAX_PERIOD_DAYS = 366
HEADER = [
    "Data do turno",
    "Empresa",
    "Vaga",
    "Valor do turno",
    "Taxa da plataforma",
    "Valor recebido",
    "Data do pagamento",
]
# Início de célula que o Excel interpreta como fórmula (injeção de CSV).
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class StatementRow:
    shift_date: date
    company: str
    vacancy: str
    gross_cents: int
    fee_cents: int
    net_cents: int
    paid_on: date


def parse_period(raw_from, raw_to, today=None):
    """Datas `AAAA-MM-DD` inclusivas. Sem nenhuma das duas, vale o mês atual até hoje."""
    today = today or timezone.localdate()
    if not raw_from and not raw_to:
        return today.replace(day=1), today
    if not raw_from or not raw_to:
        raise DomainError("Informe a data inicial e a data final do período.")
    try:
        start, end = date.fromisoformat(raw_from), date.fromisoformat(raw_to)
    except ValueError:
        raise DomainError("Data inválida; use o formato AAAA-MM-DD.") from None
    if start > end:
        raise DomainError("A data inicial não pode ser depois da data final.")
    if (end - start).days + 1 > MAX_PERIOD_DAYS:
        raise DomainError(f"O período pode ter no máximo {MAX_PERIOD_DAYS} dias.")
    return start, end


def _bounds(start, end):
    tz = timezone.get_current_timezone()
    first = datetime.combine(start, time.min, tzinfo=tz)
    last = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
    return first, last


def statement_rows(worker, start, end):
    """Uma linha por turno pago no período, do pagamento mais antigo para o mais recente."""
    first, last = _bounds(start, end)
    payouts = list(
        LedgerEntry.objects.filter(
            assignment__worker=worker,
            kind=K.WORKER_PAYOUT,
            created_at__gte=first,
            created_at__lt=last,
        )
        .select_related("assignment__vacancy__company")
        .order_by("created_at", "pk")
    )
    fees = dict(
        LedgerEntry.objects.filter(
            kind=K.PLATFORM_FEE, assignment_id__in=[p.assignment_id for p in payouts]
        )
        .values("assignment_id")
        .annotate(total=Sum("amount_cents"))
        .values_list("assignment_id", "total")
    )
    # Uma linha por turno: o repasse da hora extra (US53) soma ao do turno.
    by_shift = {}
    for payout in payouts:
        first_payout, net = by_shift.get(payout.assignment_id, (payout, 0))
        by_shift[payout.assignment_id] = (first_payout, net + payout.amount_cents)
    rows = []
    for assignment_id, (payout, net) in by_shift.items():
        vacancy = payout.assignment.vacancy
        fee = fees.get(assignment_id, 0)
        rows.append(
            StatementRow(
                shift_date=timezone.localdate(vacancy.starts_at),
                company=vacancy.company.trade_name or vacancy.company.legal_name,
                vacancy=vacancy.title,
                gross_cents=net + fee,
                fee_cents=fee,
                net_cents=net,
                paid_on=timezone.localdate(payout.created_at),
            )
        )
    return rows


def money(cents):
    """Formato brasileiro sem separador de milhar, para o Excel ler como número: 97,00."""
    return f"{cents // 100},{cents % 100:02d}"


def safe_text(value):
    """Texto vindo de outra pessoa (título, empresa) nunca vira fórmula no Excel."""
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


def build_csv(rows):
    """CSV com `;`, UTF-8 com BOM e uma linha de total no fim."""
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(HEADER)
    for row in rows:
        writer.writerow(
            [
                f"{row.shift_date:%d/%m/%Y}",
                safe_text(row.company),
                safe_text(row.vacancy),
                money(row.gross_cents),
                money(row.fee_cents),
                money(row.net_cents),
                f"{row.paid_on:%d/%m/%Y}",
            ]
        )
    writer.writerow(
        [
            "Total",
            "",
            "",
            money(sum(r.gross_cents for r in rows)),
            money(sum(r.fee_cents for r in rows)),
            money(sum(r.net_cents for r in rows)),
            "",
        ]
    )
    return buffer.getvalue()


def statement_filename(end):
    return f"extrato-conecta-ja-{end:%Y-%m}.csv"
