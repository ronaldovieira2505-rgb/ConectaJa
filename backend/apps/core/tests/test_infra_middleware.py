import logging

import pytest
from django.db.utils import OperationalError
from django.test import override_settings

from apps.core.middleware import RequestIdLogFilter
from config.settings import WHITENOISE_IMMUTABLE_FILE_TEST


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=["conectaja.example.com"])
def test_sonda_responde_mesmo_com_host_interno_desconhecido(client):
    # As sondas do Container Apps chamam pelo IP do contêiner, que não está em ALLOWED_HOSTS.
    assert client.get("/api/health/", HTTP_HOST="10.0.0.12:8000").status_code == 200
    assert client.get("/api/health/live/", HTTP_HOST="10.0.0.12:8000").status_code == 200
    # O resto da aplicação continua recusando hosts desconhecidos.
    assert client.get("/api/vacancies/", HTTP_HOST="10.0.0.12:8000").status_code == 400


@pytest.mark.django_db
@override_settings(SECURE_SSL_REDIRECT=True)
def test_sonda_nao_e_redirecionada_para_https(client):
    assert client.get("/api/health/").status_code == 200
    assert client.get("/api/health/live/").status_code == 200
    assert client.get("/api/vacancies/").status_code == 301


def test_sonda_de_vida_nao_depende_do_banco(client, monkeypatch):
    def broken_cursor(*args, **kwargs):
        raise OperationalError("db down")

    monkeypatch.setattr("apps.core.views.connection.cursor", broken_cursor)

    assert client.get("/api/health/live/").status_code == 200
    assert client.get("/api/health/").status_code == 503


@pytest.mark.django_db
def test_resposta_devolve_o_request_id_recebido(client):
    response = client.get("/api/vacancies/", HTTP_X_REQUEST_ID="abc-123")
    assert response["X-Request-ID"] == "abc-123"


@pytest.mark.django_db
@pytest.mark.parametrize("received", ["", "com espaço", "x" * 101, "quebra\nde-linha"])
def test_request_id_invalido_e_substituido_por_um_novo(client, received):
    response = client.get("/api/vacancies/", HTTP_X_REQUEST_ID=received)
    request_id = response["X-Request-ID"]
    assert request_id != received
    assert len(request_id) == 32


def test_log_fora_de_requisicao_recebe_traco():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    assert RequestIdLogFilter().filter(record)
    assert record.request_id == "-"


@pytest.mark.parametrize(
    "url, immutable",
    [
        ("/assets/index-D2l3T8Xi.js", True),
        ("/assets/index-BBdbK1bP.css", True),
        ("/index.html", False),
        ("/fonts/inter-regular.ttf", False),
        ("/favicon.svg", False),
    ],
)
def test_so_arquivos_com_hash_do_vite_ficam_em_cache_longo(url, immutable):
    assert WHITENOISE_IMMUTABLE_FILE_TEST("", url) is immutable
