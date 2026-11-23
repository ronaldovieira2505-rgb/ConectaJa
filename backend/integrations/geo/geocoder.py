"""Busca de coordenadas a partir do endereço (geocodificação).

Usada quando a empresa publica uma vaga sem informar latitude e longitude. A implementação real
consulta o Nominatim (OpenStreetMap); a simulada responde sem rede e é usada nos testes.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

from django.conf import settings
from django.utils.module_loading import import_string

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "ConectaJa/1.0 (projeto academico)"


class GeocodingError(Exception):
    """Endereço não encontrado ou serviço indisponível."""


class Geocoder:
    def geocode(self, *, street, number, city, state, zip_code="", timeout=5):
        """Devolve (latitude, longitude) como Decimal com 6 casas."""
        raise NotImplementedError


def _six(value):
    return Decimal(str(value)).quantize(Decimal("0.000001"))


class NominatimGeocoder(Geocoder):
    def geocode(self, *, street, number, city, state, zip_code="", timeout=5):
        params = {
            "street": f"{number} {street}".strip(),
            "city": city,
            "state": state,
            "country": "Brasil",
            "countrycodes": "br",
            "format": "jsonv2",
            "limit": "1",
        }
        if zip_code:
            params["postalcode"] = zip_code
        request = urllib.request.Request(
            f"{NOMINATIM_URL}?{urllib.parse.urlencode(params)}",
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                payload = json.load(response)
        except (OSError, ValueError) as error:  # URLError, HTTPError, timeout e JSON inválido
            raise GeocodingError("Serviço de mapas indisponível.") from error
        if not payload and zip_code:
            # O CEP às vezes atrapalha a busca; tenta de novo só com rua, número e cidade.
            return self.geocode(
                street=street, number=number, city=city, state=state, timeout=timeout
            )
        if not payload:
            raise GeocodingError("Endereço não encontrado no mapa.")
        return _six(payload[0]["lat"]), _six(payload[0]["lon"])


class FakeGeocoder(Geocoder):
    """Sem rede: devolve um ponto fixo em São Paulo; `fail` simula endereço não encontrado."""

    POINT = (Decimal("-23.561414"), Decimal("-46.655881"))

    def __init__(self):
        self.fail = False
        self.calls = []

    def geocode(self, *, street, number, city, state, zip_code="", timeout=5):
        self.calls.append({"street": street, "number": number, "city": city, "state": state})
        if self.fail:
            raise GeocodingError("Endereço não encontrado no mapa.")
        return self.POINT


_instance = None


def get_geocoder() -> Geocoder:
    global _instance
    if _instance is None:
        _instance = import_string(settings.GEOCODER)()
    return _instance


def reset_geocoder():
    global _instance
    _instance = None
