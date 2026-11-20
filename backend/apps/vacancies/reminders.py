"""Lembrete do turno ao prestador (US49), enviado pelo processamento de prazos.

Vale para alocações `CONFIRMADA` cujo início está a até `shift_reminder_minutes_before`.
Cada alocação recebe no máximo um lembrete (chave de idempotência da notificação).
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.core.models import Notification, PlatformParameters
from apps.core.notifications import notify_once
from apps.vacancies.models import Assignment

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
KIND = "LEMBRETE_TURNO"


def reminder_key(assignment):
    return f"lembrete-turno:{assignment.pk}"


def map_url(vacancy):
    lat, lng = vacancy.latitude, vacancy.longitude
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=17/{lat}/{lng}"


def full_address(vacancy):
    street = ", ".join(part for part in (vacancy.street, vacancy.number) if part)
    city = "/".join(part for part in (vacancy.city, vacancy.state) if part)
    return " · ".join(part for part in (street, vacancy.complement, vacancy.district, city) if part)


def day_word(starts_local, now_local):
    """"amanhã" no caso comum; "hoje" quando a aprovação veio em cima da hora."""
    days = (starts_local.date() - now_local.date()).days
    if days == 0:
        return "hoje"
    if days == 1:
        return "amanhã"
    return f"em {starts_local:%d/%m}"


def build_reminder(assignment, params, now):
    """Título, mensagem e link do lembrete."""
    vacancy = assignment.vacancy
    starts = vacancy.starts_at.astimezone(LOCAL_TZ)
    ends = vacancy.ends_at.astimezone(LOCAL_TZ)
    checkin_opens = starts - timedelta(minutes=params.checkin_open_minutes_before)
    company = vacancy.company.trade_name or vacancy.company.legal_name
    parts = [f"{vacancy.title} ({company}), {starts:%d/%m/%Y}, das {starts:%H:%M} às {ends:%H:%M}."]
    address = full_address(vacancy)
    if address:
        parts.append(f"Endereço: {address}.")
    parts.append(f"O check-in abre às {checkin_opens:%H:%M}.")
    parts.append(f"Ver no mapa: {map_url(vacancy)}")
    title = f"Lembrete: seu turno é {day_word(starts, now.astimezone(LOCAL_TZ))}"
    return title, " ".join(parts), f"/vagas/{vacancy.pk}"


def due_assignments(now, params):
    """Confirmadas, ainda não iniciadas e dentro da janela do lembrete."""
    window_end = now + timedelta(minutes=params.shift_reminder_minutes_before)
    return Assignment.objects.filter(
        status=Assignment.Status.CONFIRMED,
        vacancy__starts_at__gt=now,
        vacancy__starts_at__lte=window_end,
    ).select_related("vacancy__company", "worker__user")


def send_due_reminders(now=None, params=None):
    """Envia os lembretes pendentes. Idempotente; devolve quantos foram enviados agora."""
    now = now or timezone.now()
    params = params or PlatformParameters.get()
    due = list(due_assignments(now, params))
    already_sent = set(
        Notification.objects.filter(
            dedup_key__in=[reminder_key(a) for a in due]
        ).values_list("dedup_key", flat=True)
    )
    sent = 0
    for assignment in due:
        key = reminder_key(assignment)
        if key in already_sent:
            continue
        title, message, link = build_reminder(assignment, params, now)
        if notify_once(assignment.worker.user, key, KIND, title, message, link):
            sent += 1
    return sent
