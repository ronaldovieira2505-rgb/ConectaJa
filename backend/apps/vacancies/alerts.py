"""Alerta "Nova vaga perto de você" (US19), enviado quando a vaga é publicada (paga).

Roda depois de confirmado o pagamento e nunca o desfaz: se o envio falhar, a vaga continua
publicada. No máximo um alerta por vaga e cinco por dia para cada prestador.
"""

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.core.models import Notification, PlatformParameters
from apps.core.notifications import notify_once
from apps.vacancies.application_services import has_overlap
from apps.vacancies.models import Vacancy
from apps.workers.availability import has_availability, matches
from apps.workers.models import Worker
from integrations.geo import haversine_distance_m

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
KIND = "ALERTA_VAGA"
DAILY_LIMIT = 5


def alert_key(vacancy, worker):
    return f"alerta-vaga:{vacancy.pk}:{worker.pk}"


def alerts_today(worker, now):
    start = datetime.combine(timezone.localdate(now), time.min, tzinfo=LOCAL_TZ)
    return Notification.objects.filter(
        user=worker.user, kind=KIND, created_at__gte=start, created_at__lt=start + timedelta(days=1)
    ).count()


def distance_km(worker, vacancy):
    meters = haversine_distance_m(
        worker.home_latitude, worker.home_longitude, vacancy.latitude, vacancy.longitude
    )
    return meters / 1000


def wants(worker, vacancy, now):
    """Distância (km) se o prestador deve receber o alerta desta vaga; senão None."""
    if worker.is_suspended(now) or not worker.pix_key:
        return None
    if worker.skills and vacancy.category not in worker.skills:
        return None
    if worker.alert_only_my_schedule and has_availability(worker):
        if not matches(worker, vacancy.starts_at):
            return None
    km = distance_km(worker, vacancy)
    if km > worker.alert_radius_km:
        return None
    if has_overlap(worker, vacancy):
        return None
    return km


def message(vacancy, km, params):
    starts = vacancy.starts_at.astimezone(LOCAL_TZ)
    net = params.worker_net_cents(vacancy.pay_per_person_cents)
    reais, cents = divmod(net, 100)
    money = f"R$ {reais:,}".replace(",", ".") + f",{cents:02d}"
    distance = f"{km:.1f}".replace(".", ",")
    return (
        f"{vacancy.title} · você recebe {money} · {starts:%d/%m} às {starts:%H:%M} "
        f"· {distance} km de casa"
    )


def send_vacancy_alerts(vacancy_id, now=None):
    """Envia os alertas da vaga recém-publicada. Devolve quantos foram enviados."""
    now = now or timezone.now()
    vacancy = Vacancy.objects.filter(pk=vacancy_id, status=Vacancy.Status.PUBLISHED).first()
    if vacancy is None:
        return 0
    params = PlatformParameters.get()
    sent = 0
    workers = Worker.objects.filter(
        alerts_enabled=True,
        verification_status=Worker.VerificationStatus.APPROVED,
        user__is_active=True,
        home_latitude__isnull=False,
        home_longitude__isnull=False,
    ).select_related("user")
    for worker in workers:
        km = wants(worker, vacancy, now)
        if km is None or alerts_today(worker, now) >= DAILY_LIMIT:
            continue
        if notify_once(
            worker.user,
            alert_key(vacancy, worker),
            KIND,
            "Nova vaga perto de você",
            message(vacancy, km, params),
            link=f"/vagas/{vacancy.pk}",
        ):
            sent += 1
    return sent


def send_safely(vacancy_id):
    """Chamado depois do pagamento: um erro aqui só vai para o log."""
    try:
        send_vacancy_alerts(vacancy_id)
    except Exception:  # alerta nunca derruba a publicação
        logger.exception("Falha ao enviar alertas da vaga #%s", vacancy_id)
