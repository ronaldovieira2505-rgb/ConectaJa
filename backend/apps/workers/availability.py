"""Dias e horários em que o prestador está disponível (US10). Só informa: não impede candidatura.

Faixas no horário de São Paulo: manhã 6h–12h, tarde 12h–18h e noite 18h–6h. Uma vaga "cai" na
disponibilidade pelo dia e pela faixa do horário de início.
"""

from zoneinfo import ZoneInfo

from django.db import transaction

from apps.core.exceptions import DomainError

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
# Ordem de `datetime.weekday()`: segunda = 0.
DAYS = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
DAY_LABELS = {
    "SEG": "Seg",
    "TER": "Ter",
    "QUA": "Qua",
    "QUI": "Qui",
    "SEX": "Sex",
    "SAB": "Sáb",
    "DOM": "Dom",
}
PERIODS = ["MANHA", "TARDE", "NOITE"]
PERIOD_LABELS = {"MANHA": "manhã", "TARDE": "tarde", "NOITE": "noite"}
FIELDS = {"availability_days": DAYS, "availability_periods": PERIODS}


def _clean(value, allowed, what):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DomainError(f"Envie os {what} como uma lista.")
    if len(set(value)) != len(value):
        raise DomainError(f"Cada um dos {what} só pode aparecer uma vez.")
    if any(item not in allowed for item in value):
        raise DomainError(f"Há {what} inválidos.")
    return [item for item in allowed if item in value]  # ordem da semana / do dia


def clean_days(value):
    return _clean(value, DAYS, "dias")


def clean_periods(value):
    return _clean(value, PERIODS, "horários")


@transaction.atomic
def update_availability(worker, changes):
    """Salva só os campos enviados (`availability_days`, `availability_periods`)."""
    cleaned = {}
    if "availability_days" in changes:
        cleaned["availability_days"] = clean_days(changes["availability_days"])
    if "availability_periods" in changes:
        cleaned["availability_periods"] = clean_periods(changes["availability_periods"])
    for field, value in cleaned.items():
        setattr(worker, field, value)
    if cleaned:
        worker.save(update_fields=list(cleaned))
    return worker


def has_availability(worker):
    return bool(worker.availability_days) and bool(worker.availability_periods)


def period_of(hour):
    if 6 <= hour < 12:
        return "MANHA"
    if 12 <= hour < 18:
        return "TARDE"
    return "NOITE"


def matches(worker, starts_at):
    """O início da vaga (em São Paulo) cai num dia e numa faixa que o prestador marcou?"""
    local = starts_at.astimezone(LOCAL_TZ)
    return (
        DAYS[local.weekday()] in worker.availability_days
        and period_of(local.hour) in worker.availability_periods
    )


def _days_text(days):
    """["SEG".."SEX"] → "Seg–Sex"; ["SEG", "QUA"] → "Seg, Qua"; sequências viram intervalos."""
    indexes = [DAYS.index(day) for day in days]
    runs, start = [], None
    for i, index in enumerate(indexes):
        if start is None:
            start = index
        nxt = indexes[i + 1] if i + 1 < len(indexes) else None
        if nxt != index + 1:
            runs.append((start, index))
            start = None
    parts = []
    for first, last in runs:
        if last - first >= 2:
            parts.append(f"{DAY_LABELS[DAYS[first]]}–{DAY_LABELS[DAYS[last]]}")
        else:
            parts.extend(DAY_LABELS[DAYS[i]] for i in range(first, last + 1))
    return ", ".join(parts)


def _join(items):
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} e {items[-1]}"


def summary(worker):
    """"Seg–Sex · manhã e tarde"; vazio quando falta dia ou faixa."""
    if not has_availability(worker):
        return ""
    periods = [PERIOD_LABELS[p] for p in worker.availability_periods]
    return f"{_days_text(worker.availability_days)} · {_join(periods)}"


def serialize(worker):
    return {
        "days": worker.availability_days,
        "periods": worker.availability_periods,
        "summary": summary(worker),
    }
