"""Configuração dos alertas de vaga do prestador (US19) e a localização de casa usada neles."""

from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.core.exceptions import DomainError

RADII_KM = (5, 10, 20, 50)
FIELDS = {
    "alerts_enabled",
    "alert_radius_km",
    "alert_only_my_schedule",
    "home_latitude",
    "home_longitude",
}


def _bool(value, name):
    if not isinstance(value, bool):
        raise DomainError(f"Valor inválido em {name}.")
    return value


def _coordinate(value, limit, name):
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise DomainError(f"{name} inválida.") from None
    if not number.is_finite() or abs(number) > limit:
        raise DomainError(f"{name} fora da faixa válida.")
    return number.quantize(Decimal("0.000001"))


@transaction.atomic
def update_alert_settings(worker, changes):
    """Salva só os campos enviados. Ligar os alertas exige a localização de casa."""
    cleaned = {}
    if "alerts_enabled" in changes:
        cleaned["alerts_enabled"] = _bool(changes["alerts_enabled"], "alerts_enabled")
    if "alert_only_my_schedule" in changes:
        cleaned["alert_only_my_schedule"] = _bool(
            changes["alert_only_my_schedule"], "alert_only_my_schedule"
        )
    if "alert_radius_km" in changes:
        radius = changes["alert_radius_km"]
        if isinstance(radius, bool) or radius not in RADII_KM:
            raise DomainError("Escolha um raio de 5, 10, 20 ou 50 km.")
        cleaned["alert_radius_km"] = radius
    if "home_latitude" in changes or "home_longitude" in changes:
        lat = _coordinate(changes.get("home_latitude"), 90, "Latitude")
        lng = _coordinate(changes.get("home_longitude"), 180, "Longitude")
        if (lat is None) != (lng is None):
            raise DomainError("Informe latitude e longitude juntas.")
        cleaned["home_latitude"], cleaned["home_longitude"] = lat, lng
    enabled = cleaned.get("alerts_enabled", worker.alerts_enabled)
    has_home = cleaned.get("home_latitude", worker.home_latitude) is not None
    if enabled and not has_home:
        raise DomainError("Defina a sua localização de casa para receber alertas.")
    for field, value in cleaned.items():
        setattr(worker, field, value)
    if cleaned:
        worker.save(update_fields=list(cleaned))
    return worker


def serialize(worker):
    """A localização de casa nunca sai em claro: só se ela está definida."""
    return {
        "enabled": worker.alerts_enabled,
        "radius_km": worker.alert_radius_km,
        "only_my_schedule": worker.alert_only_my_schedule,
        "has_home_location": worker.home_latitude is not None,
    }
