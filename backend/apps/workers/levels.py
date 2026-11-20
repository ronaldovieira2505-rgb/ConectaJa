"""Níveis do prestador (US65): Novo, Bronze, Prata e Ouro.

Base do nível (valores em `PlatformParameters`):
- Bronze: turnos pagos ≥ `level_bronze_shifts` e nota média ≥ `level_bronze_rating`.
- Prata: turnos pagos ≥ `level_silver_shifts`, nota ≥ `level_silver_rating` e nenhuma falta
  na janela `level_window_days`.
- Ouro: turnos pagos ≥ `level_gold_shifts`, nota ≥ `level_gold_rating` e nenhuma falta na janela.

Cada cancelamento tardio na janela derruba um nível (US72: "rebaixamento de status"); por isso
Ouro também exige nenhum cancelamento tardio. Os turnos pagos e a nota consideram todo o
histórico; faltas e cancelamentos tardios, só a janela. A nota é a média exibida (1 casa).
Sem avaliações não há nota, e os níveis que pedem nota não são atingidos.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.core.models import PlatformParameters, StateTransition
from apps.core.notifications import notify
from apps.workers.models import Worker

L = Worker.Level
ORDER = [L.NEW, L.BRONZE, L.SILVER, L.GOLD]
LATE_CANCEL_REASON = "Cancelamento tardio"


@dataclass(frozen=True)
class Metrics:
    paid_shifts: int
    rating: Decimal | None
    no_shows: int
    late_cancels: int


def metrics(worker, *, now=None, params=None):
    # Importados aqui: vagas dependem de prestadores, não o contrário.
    from apps.vacancies.models import Assignment, Review

    now = now or timezone.now()
    params = params or PlatformParameters.get()
    since = now - timedelta(days=params.level_window_days)
    S = Assignment.Status
    row = Review.objects.filter(
        assignment__worker=worker, direction=Review.Direction.COMPANY_TO_WORKER
    ).aggregate(avg=Avg("rating"), total=Count("pk"))
    rating = None
    if row["total"]:
        rating = Decimal(str(row["avg"])).quantize(Decimal("0.1"), ROUND_HALF_UP)
    history = StateTransition.objects.filter(
        entity_type="Assignment",
        entity_id__in=worker.assignments.values("pk"),
        created_at__gte=since,
    )
    return Metrics(
        paid_shifts=worker.assignments.filter(status=S.PAID).count(),
        rating=rating,
        no_shows=history.filter(to_state=S.NO_SHOW).count(),
        late_cancels=history.filter(
            to_state=S.CANCELLED_BY_WORKER, reason=LATE_CANCEL_REASON
        ).count(),
    )


def requirements(level, params):
    """(turnos pagos, nota mínima, exige nenhuma falta) de cada nível acima de Novo."""
    return {
        L.BRONZE: (params.level_bronze_shifts, params.level_bronze_rating, False),
        L.SILVER: (params.level_silver_shifts, params.level_silver_rating, True),
        L.GOLD: (params.level_gold_shifts, params.level_gold_rating, True),
    }[level]


def _meets(level, m, params):
    shifts, rating, no_absences = requirements(level, params)
    return (
        m.paid_shifts >= shifts
        and m.rating is not None
        and m.rating >= rating
        and not (no_absences and m.no_shows)
    )


def base_level(m, params):
    for level in (L.GOLD, L.SILVER, L.BRONZE):
        if _meets(level, m, params):
            return level
    return L.NEW


def compute(worker, *, now=None, params=None):
    params = params or PlatformParameters.get()
    m = metrics(worker, now=now, params=params)
    index = max(0, ORDER.index(base_level(m, params)) - m.late_cancels)
    return ORDER[index], m


def _rating_text(value):
    return f"{value:.1f}".replace(".", ",")


def missing_for(level, m, params):
    """O que falta para chegar a `level`, em frases curtas."""
    shifts, rating, no_absences = requirements(level, params)
    missing = []
    if m.paid_shifts < shifts:
        count = shifts - m.paid_shifts
        missing.append(f"{count} {'turno pago' if count == 1 else 'turnos pagos'}")
    if m.rating is None:
        missing.append(
            f"nota média de pelo menos {_rating_text(rating)} (você ainda não tem avaliações)"
        )
    elif m.rating < rating:
        missing.append(f"nota média de pelo menos {_rating_text(rating)}")
    if no_absences and m.no_shows:
        missing.append(f"nenhuma falta nos últimos {params.level_window_days} dias")
    if m.late_cancels:
        missing.append(f"nenhum cancelamento tardio nos últimos {params.level_window_days} dias")
    return missing


def serialize(worker, *, now=None, params=None):
    """Nível atual e o que falta para o próximo ("Faltam 3 turnos pagos para o nível Bronze")."""
    params = params or PlatformParameters.get()
    level, m = compute(worker, now=now, params=params)
    current = Worker.Level(worker.level)
    data = {"code": current.value, "label": current.label, "next": None}
    if current == L.GOLD:
        return data
    target = ORDER[ORDER.index(current) + 1]
    missing = missing_for(target, m, params)
    data["next"] = {
        "code": target.value,
        "label": target.label,
        "missing": missing,
        "summary": f"Faltam {' e '.join(missing)} para o nível {target.label}" if missing else "",
    }
    return data


def _drop_reason(m, params, fallback):
    if m.late_cancels:
        return f"cancelamento tardio nos últimos {params.level_window_days} dias"
    if m.no_shows:
        return f"falta nos últimos {params.level_window_days} dias"
    return fallback


@transaction.atomic
def recalculate(worker, *, reason="", now=None):
    """Recalcula e grava o nível. Só avisa quando muda (recalcular de novo não duplica)."""
    now = now or timezone.now()
    params = PlatformParameters.get()
    worker = Worker.objects.select_for_update().get(pk=worker.pk)
    level, m = compute(worker, now=now, params=params)
    old = worker.level
    if level == old:
        return worker
    worker.level = level
    worker.save(update_fields=["level"])
    StateTransition.objects.create(
        entity_type="WorkerLevel",
        entity_id=worker.pk,
        from_state=old,
        to_state=level,
        reason=reason,
        created_at=now,
    )
    label = Worker.Level(level).label
    if ORDER.index(level) > ORDER.index(old):
        notify(
            worker.user,
            "NIVEL",
            f"Parabéns, você subiu para o nível {label}",
            "Continue assim: turnos pagos, boas avaliações e nenhuma falta mantêm o seu nível.",
            link="/prestador/perfil",
        )
    else:
        why = _drop_reason(m, params, reason or "os critérios do nível deixaram de ser cumpridos")
        notify(
            worker.user,
            "NIVEL",
            f"Seu nível caiu para {label}",
            f"Motivo: {why}.",
            link="/prestador/perfil",
        )
    return worker
