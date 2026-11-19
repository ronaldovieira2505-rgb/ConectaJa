import pytest
from django.core.cache import cache

from integrations.cnpj import get_cnpj_lookup, reset_cnpj_lookup
from integrations.payments import get_gateway, reset_gateway


@pytest.fixture(autouse=True)
def fake_gateway():
    """PSP simulado limpo a cada teste (os testes nunca chamam serviços externos)."""
    reset_gateway()
    yield get_gateway()
    reset_gateway()


@pytest.fixture(autouse=True)
def fake_cnpj_lookup(settings):
    """BrasilAPI simulada a cada teste (nenhum teste chama a internet)."""
    settings.CNPJ_LOOKUP = "integrations.cnpj.fake.FakeCnpjLookup"
    reset_cnpj_lookup()
    yield get_cnpj_lookup()
    reset_cnpj_lookup()


@pytest.fixture(autouse=True)
def no_https_redirect(settings):
    """O CI roda com DEBUG=false e o cliente de teste usa HTTP: sem redirecionar para HTTPS."""
    settings.SECURE_SSL_REDIRECT = False


@pytest.fixture(autouse=True)
def fast_password_hasher(settings):
    """Hash barato só nos testes: o PBKDF2 de produção deixava a suíte lenta."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def clean_cache():
    """Contadores do limite de tentativas não vazam de um teste para o outro."""
    cache.clear()
    yield
    cache.clear()
