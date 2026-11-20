"""Middlewares de infraestrutura: sondas de saúde e identificador da requisição."""

import contextvars
import logging
import re
import uuid

from apps.core import views

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_request_id = contextvars.ContextVar("request_id", default="-")

HEALTH_PATHS = {
    "/api/health/": True,  # prontidão: confere o banco
    "/api/health/live/": False,  # vida: só o processo
}


class HealthCheckMiddleware:
    """Responde as sondas antes da checagem de ALLOWED_HOSTS e do redirecionamento HTTPS.

    As sondas da hospedagem (Container Apps, App Service, Docker) chamam pelo IP interno e por
    HTTP; sem isso o Django responderia 400 (host desconhecido) ou 301 e a sonda falharia.
    Fica em primeiro lugar no MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        check_database = HEALTH_PATHS.get(request.path)
        if check_database is not None and request.method in ("GET", "HEAD"):
            return views.health_response(check_database=check_database)
        return self.get_response(request)


def current_request_id():
    return _request_id.get()


class RequestIdMiddleware:
    """Liga logs e resposta pelo mesmo identificador.

    Reaproveita o `X-Request-ID` recebido (se for seguro) ou gera um novo, devolve no cabeçalho
    da resposta e o expõe aos logs pelo `RequestIdLogFilter`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        received = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = received if _VALID_REQUEST_ID.match(received) else uuid.uuid4().hex
        request.request_id = request_id
        token = _request_id.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response[REQUEST_ID_HEADER] = request_id
        return response


class RequestIdLogFilter(logging.Filter):
    """Acrescenta `request_id` a todo registro de log (fora de requisição: "-")."""

    def filter(self, record):
        record.request_id = current_request_id()
        return True
